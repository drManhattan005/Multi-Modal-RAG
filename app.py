"""
app.py — FastAPI voice-RAG backend.

All heavy model loading happens inside the lifespan() context manager so it
only executes in the real Uvicorn worker process, never in the file-watcher
parent spawned by --reload.  This prevents the Qdrant portalocker conflict.

Endpoints:
  GET  /           → index.html
  GET  /health     → status JSON
  POST /reset      → clear session history
  POST /ask        → question + optional voice metadata → answer JSON
"""

from __future__ import annotations

import os
from collections import defaultdict
from contextlib import asynccontextmanager

import torch
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
import httpx
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Module-level singletons — populated inside lifespan(), used by route handlers
# ---------------------------------------------------------------------------
qdrant: QdrantClient | None = None
embedder = None

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

QDRANT_PATH = "qdrant_data"
COLLECTION_NAME = "veloit_handbook_chunks"
EMBED_MODEL_NAME = "intfloat/multilingual-e5-base"
MODEL_CACHE = "models"

# Ollama LLM Configuration (single source of truth: .env with defaults)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:1.5b")
LLM_NUM_CTX = int(os.getenv("LLM_NUM_CTX", "2048"))
LLM_NUM_THREAD = int(os.getenv("LLM_NUM_THREAD", "4"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))
LLM_NUM_PREDICT = int(os.getenv("LLM_NUM_PREDICT", "512"))

MAX_HISTORY_TURNS = 6
MAX_SESSION_CHARS = 10000
MAX_CONTEXT_CHARS = 4000
MIN_RETRIEVAL_SCORE = 0.42
RETRIEVAL_TOP_K = 3

# ---------------------------------------------------------------------------
# Device selection
# ---------------------------------------------------------------------------

# Device is resolved at module level (cheap, no I/O)
if torch.cuda.is_available():
    device = "cuda"
elif torch.backends.mps.is_available():
    device = "mps"
else:
    device = "cpu"

print(f"[app] Compute device: {device}")

# ---------------------------------------------------------------------------
# Lifespan — all heavy I/O and model loading happens HERE, in the worker only.
# Using a lifespan context manager is the FastAPI-idiomatic way to do startup/
# shutdown and it is never called by uvicorn's file-watcher parent process.
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global qdrant, embedder

    print("[app] Connecting to Qdrant…")
    qdrant = QdrantClient(path=QDRANT_PATH)

    print("[app] Loading embedder…")
    embedder = SentenceTransformer(
        EMBED_MODEL_NAME, cache_folder=MODEL_CACHE, device=device
    )

    # Startup health check for Ollama and required model
    print(f"[app] Verifying Ollama connection at {OLLAMA_BASE_URL}…")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if resp.status_code == 200:
                tags = resp.json().get("models", [])
                pulled_models = [m.get("name", "") for m in tags]
                found = any(
                    name == LLM_MODEL or name == f"{LLM_MODEL}:latest" or name.startswith(f"{LLM_MODEL}:") or LLM_MODEL.startswith(name)
                    for name in pulled_models
                )
                if found:
                    print(f"[app] Ollama model '{LLM_MODEL}' verified successfully.")
                else:
                    print(
                        f"[ERROR] Model '{LLM_MODEL}' is not pulled in Ollama.\n"
                        f"Run: ollama pull {LLM_MODEL}"
                    )
            else:
                print(f"[ERROR] Ollama returned HTTP {resp.status_code} at {OLLAMA_BASE_URL}.")
    except Exception as exc:
        print(
            f"[ERROR] Could not connect to Ollama at {OLLAMA_BASE_URL} ({exc}).\n"
            f"Ensure Ollama is running ('ollama serve') and model is pulled ('ollama pull {LLM_MODEL}')."
        )

    print("[app] Embedder and pipeline ready — server ready.")
    yield
    print("[app] Shutting down.")

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

chat_memory: dict[str, list] = defaultdict(list)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Veloit Voice RAG", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ---------------------------------------------------------------------------
# Retrieval helpers  (unchanged logic, extracted for clarity)
# ---------------------------------------------------------------------------

def estimate_chars(messages: list) -> int:
    return sum(len(m.get("role", "")) + len(m.get("content", "")) for m in messages)


def prune_session_history(history: list) -> list:
    while len(history) > MAX_HISTORY_TURNS * 2:
        history.pop(0)
    while history and estimate_chars(history) > MAX_SESSION_CHARS:
        history.pop(0)
    return history


def retrieve_chunks(query: str, limit: int = RETRIEVAL_TOP_K):
    query_vec = embedder.encode([f"query: {query}"], normalize_embeddings=True)[0]
    response = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vec.tolist(),
        limit=limit * 3,
        with_payload=True,
        with_vectors=False,
    )

    seen: set = set()
    deduped = []
    for point in response.points:
        payload = point.payload or {}
        chunk_id = payload.get("chunk_id")
        dedupe_key = chunk_id or (
            payload.get("source_file"),
            payload.get("section_title"),
            payload.get("subsection_title"),
            (payload.get("text") or "")[:120],
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped.append(point)
        if len(deduped) >= limit:
            break

    return deduped


def build_context(points) -> str:
    blocks = []
    for i, point in enumerate(points, start=1):
        p = point.payload or {}
        blocks.append(
            f"[{i}] section={p.get('section_title')} | "
            f"subsection={p.get('subsection_title')} | "
            f"file={p.get('source_file')}\n{p.get('text')}"
        )
    return "\n\n".join(blocks)


def build_sources(points) -> list:
    items = []
    for point in points:
        p = point.payload or {}
        items.append(
            {
                "score": round(float(point.score), 4) if point.score is not None else None,
                "chunk_id": p.get("chunk_id"),
                "section_title": p.get("section_title"),
                "subsection_title": p.get("subsection_title"),
                "source_file": p.get("source_file"),
            }
        )
    return items


def build_debug_chunks(points) -> list:
    items = []
    for point in points:
        p = point.payload or {}
        items.append(
            {
                "score": round(float(point.score), 4) if point.score is not None else None,
                "chunk_id": p.get("chunk_id"),
                "section_title": p.get("section_title"),
                "subsection_title": p.get("subsection_title"),
                "source_file": p.get("source_file"),
                "preview": (p.get("text") or "")[:280],
            }
        )
    return items


def is_grounded(answer: str, context: str) -> bool:
    a_words = set(answer.lower().split())
    c_words = set(context.lower().split())
    return len(a_words & c_words) >= 5


# Language code → human-readable name used in the answer prompt.
_LANG_NAMES: dict[str, str] = {
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "nl": "Dutch",
    "pt": "Portuguese",
    "pl": "Polish",
    "sv": "Swedish",
    "da": "Danish",
    "fi": "Finnish",
    "nb": "Norwegian",
    "cs": "Czech",
    "sk": "Slovak",
    "hu": "Hungarian",
    "ro": "Romanian",
    "bg": "Bulgarian",
    "hr": "Croatian",
    "el": "Greek",
    "tr": "Turkish",
}

DEFAULT_LANG = "en"


def normalize_language(code: str | None) -> str:
    """
    Normalise language to a supported code in _LANG_NAMES; default 'en'.
    """
    if not code:
        return DEFAULT_LANG
    c = code.strip().lower()
    if c in ("", "none", "auto", "null"):
        return DEFAULT_LANG
    if "-" in c:
        c = c.split("-")[0]
    elif "_" in c:
        c = c.split("_")[0]
    return c if c in _LANG_NAMES else DEFAULT_LANG


SYSTEM_PROMPT = (
    "You are a concise and factual handbook assistant. "
    "Answer only from the supplied context. "
    "Do not mention instructions or context. "
    "If evidence is missing, say so clearly."
)

_ANSWER_PROMPT_TEMPLATE = """\
Use ONLY the context below to answer the user's question.

Rules:
- Answer in {lang_name} (language code: {lang_code}).
- Do not translate or paraphrase the context; ground your answer directly in it.
- Do not mention these instructions or the word "context".
- Be concise and direct.
- Include source references like [1] or [2] where helpful.
- If the answer is not found in the context, reply in {lang_name}: \
"I could not find that in the handbook."

Context (English):
{context}

User question ({lang_name}):
{question}
"""


def generate_answer(
    user_message: str,
    context: str,
    history: list,
    target_language: str = "en",
) -> str:
    lang_name = _LANG_NAMES.get(target_language, target_language.upper())
    compact_context = context[:MAX_CONTEXT_CHARS]

    prompt = _ANSWER_PROMPT_TEMPLATE.format(
        lang_name=lang_name,
        lang_code=target_language,
        context=compact_context,
        question=user_message,
    )

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for item in history[-8:]:
        messages.append({"role": item["role"], "content": item["content"]})
    messages.append({"role": "user", "content": prompt})

    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": LLM_MODEL,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "num_ctx": LLM_NUM_CTX,
                        "num_thread": LLM_NUM_THREAD,
                        "temperature": LLM_TEMPERATURE,
                        "num_predict": LLM_NUM_PREDICT,
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()
            answer = data.get("message", {}).get("content", "").strip()
    except Exception as exc:
        print(f"[app] Error during Ollama generation: {exc}")
        answer = "I could not generate an answer due to an error connecting to the language model."

    return answer


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class AskRequest(BaseModel):
    question: str
    session_id: str = "default"
    debug: bool = False
    language: str | None = None
    preset_language: str | None = None
    lang_override: str | None = None
    target_language: str | None = None
    normalized_query_en: str | None = None
    transcript: str | None = None


class ResetRequest(BaseModel):
    session_id: str = "default"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "device": device,
        "session_mode": "single-process in-memory",
    }


@app.post("/reset")
async def reset(body: ResetRequest):
    chat_memory[body.session_id] = []
    return {"ok": True, "session_id": body.session_id}


@app.post("/ask")
async def ask(body: AskRequest):
    """
    Text or voice-derived question → grounded answer in target language.

    When called from the voice flow, body.normalized_query_en is already set
    and is used directly for retrieval. When called from the text flow,
    body.question is used directly.
    """
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    session_id = body.session_id
    history = chat_memory[session_id]
    prune_session_history(history)

    # --- Determine target language -----------------------------------------
    selected_language = normalize_language(
        body.language or body.preset_language or body.lang_override or body.target_language
    )
    print(f"[lang] selected={selected_language}")

    # --- Determine retrieval query -----------------------------------------
    retrieval_query = body.normalized_query_en or question

    # --- Retrieve English chunks -------------------------------------------
    points = retrieve_chunks(retrieval_query, limit=RETRIEVAL_TOP_K)
    top_score = max((float(p.score) for p in points if p.score is not None), default=0.0)
    context = build_context(points)

    # --- Generate answer in target language ----------------------------------
    if not points or top_score < MIN_RETRIEVAL_SCORE:
        not_found = {
            "de": "Dazu konnte ich nichts im Handbuch finden.",
            "fr": "Je n'ai pas trouvé cela dans le manuel.",
            "es": "No encontré eso en el manual.",
            "it": "Non ho trovato questo nel manuale.",
        }
        answer = not_found.get(
            selected_language,
            "I could not find a reliable answer in the handbook for that.",
        )
    else:
        answer = generate_answer(question, context, history, target_language=selected_language)

    # --- Update session history -------------------------------------------
    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": answer})
    prune_session_history(history)

    sources = build_sources(points)
    session_chars = estimate_chars(history)
    session_fill_ratio = min(session_chars / MAX_SESSION_CHARS, 1.0)

    response: dict = {
        "session_id": session_id,
        "transcript": body.transcript or question,
        "language": selected_language,
        "normalized_query_en": retrieval_query,
        "answer": answer,
        "sources": sources,
        "meta": {
            "top_score": round(top_score, 4),
            "retrieved_chunks": len(points),
            "session_chars": session_chars,
            "session_char_limit": MAX_SESSION_CHARS,
            "session_fill_ratio": session_fill_ratio,
            "history_messages": len(history),
            "context_chars_used": min(len(context), MAX_CONTEXT_CHARS),
            "context_char_limit": MAX_CONTEXT_CHARS,
        },
    }

    if body.debug:
        response["debug"] = {
            "retrieved_chunks": build_debug_chunks(points),
            "context_preview": context[:1200],
        }

    return response


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
