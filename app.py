"""
app.py — FastAPI voice-RAG backend.

All heavy model loading happens inside the lifespan() context manager so it
only executes in the real Uvicorn worker process, never in the file-watcher
parent spawned by --reload.  This prevents the Qdrant portalocker conflict.

Endpoints:
  GET  /           → index.html
  GET  /health     → status JSON
  POST /reset      → clear session history
  POST /transcribe → audio bytes → transcript + lang
  POST /ask        → question + optional voice metadata → answer JSON
  POST /voice-ask  → audio blob → full answer JSON (combined pipeline)
"""

from __future__ import annotations

import os
from collections import defaultdict
from contextlib import asynccontextmanager

import av
import av.error
import torch
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForCausalLM, AutoTokenizer

from normalizer import normalize_to_english

# ---------------------------------------------------------------------------
# Module-level singletons — populated inside lifespan(), used by route handlers
# ---------------------------------------------------------------------------
qdrant: QdrantClient | None = None
embedder = None
tokenizer = None
llm = None
_asr_transcribe = None

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

QDRANT_PATH = "qdrant_data"
COLLECTION_NAME = "veloit_handbook_chunks"
EMBED_MODEL_NAME = "intfloat/multilingual-e5-base"
LLM_NAME = "utter-project/EuroLLM-1.7B-Instruct"
MODEL_CACHE = "models"

MAX_HISTORY_TURNS = 6
MAX_SESSION_CHARS = 10000
MAX_CONTEXT_CHARS = 8000
MIN_RETRIEVAL_SCORE = 0.42
RETRIEVAL_TOP_K = 5

# Max audio upload size: 15 MB  (roughly 60 s of webm at 192 kbps)
MAX_AUDIO_BYTES = 15 * 1024 * 1024

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
    global qdrant, embedder, tokenizer, llm, _asr_transcribe

    print("[app] Connecting to Qdrant…")
    qdrant = QdrantClient(path=QDRANT_PATH)

    print("[app] Loading embedder…")
    embedder = SentenceTransformer(
        EMBED_MODEL_NAME, cache_folder=MODEL_CACHE, device=device
    )

    print("[app] Loading EuroLLM tokenizer…")
    tokenizer = AutoTokenizer.from_pretrained(LLM_NAME, cache_dir=MODEL_CACHE)

    print("[app] Loading EuroLLM model…")
    _llm = AutoModelForCausalLM.from_pretrained(
        LLM_NAME,
        cache_dir=MODEL_CACHE,
        dtype=torch.float16,
    )
    _llm.to(device)
    _llm.eval()
    llm = _llm

    print("[app] Loading ASR module (Faster-Whisper)…")
    from asr import transcribe as _asr_fn
    _asr_transcribe = _asr_fn

    print("[app] All models loaded — server ready.")
    yield
    # Shutdown: nothing explicit needed; Python GC handles model cleanup.
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

    inputs = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
    ).to(device)

    with torch.no_grad():
        outputs = llm.generate(
            **inputs,
            do_sample=False,
            max_new_tokens= 250,
            repetition_penalty=1.1,
            pad_token_id=tokenizer.eos_token_id,
        )

    new_tokens = outputs[0][inputs["input_ids"].shape[-1]:]
    answer = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

 
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
        "asr": "faster-whisper",
    }


@app.post("/reset")
async def reset(body: ResetRequest):
    chat_memory[body.session_id] = []
    return {"ok": True, "session_id": body.session_id}


@app.post("/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...),
    language: str | None = Form(default=None),
    preset_language: str | None = Form(default=None),
    lang_override: str | None = Form(default=None),
):
    """
    Accept a browser audio blob (webm/ogg/mp4) and return transcript + language.
    """
    selected_language = normalize_language(language or preset_language or lang_override)
    audio_bytes = await audio.read()
    filename = audio.filename or "recording"
    content_type = audio.content_type or "unknown"
    size_bytes = len(audio_bytes) if audio_bytes else 0

    print(f"[transcribe] Received '{filename}' ({content_type}, {size_bytes} bytes), lang={selected_language}")

    if not audio_bytes or size_bytes < 100:
        print(f"[transcribe] Rejected: audio data empty or too small ({size_bytes} bytes)")
        raise HTTPException(status_code=400, detail="No audio data received or audio too small.")

    if size_bytes > MAX_AUDIO_BYTES:
        print(f"[transcribe] Rejected: audio file exceeds limit ({size_bytes} bytes)")
        raise HTTPException(
            status_code=413,
            detail=f"Audio too large. Maximum is {MAX_AUDIO_BYTES // 1024 // 1024} MB.",
        )

    try:
        result = _asr_transcribe(
            audio_bytes,
            language=selected_language,
        )
    except (av.error.InvalidDataError, av.error.FFmpegError, av.AVError, ValueError) as exc:
        print(f"[transcribe] Audio decode error for '{filename}': {exc}")
        raise HTTPException(
            status_code=400,
            detail="Invalid or corrupted audio upload. Please record again.",
        )
    except Exception as exc:
        print(f"[transcribe] Unexpected ASR failure for '{filename}': {exc}")
        raise HTTPException(
            status_code=500,
            detail="Speech recognition failed. Please try again.",
        )

    transcript = result.get("transcript", "").strip()

    if not transcript:
        print(f"[transcribe] Empty transcript returned for '{filename}'")
        raise HTTPException(
            status_code=422,
            detail="Could not transcribe audio. Please speak clearly and try again.",
        )

    print(f"[transcribe] Success: [{selected_language}] '{transcript}'")
    return {
        "transcript": transcript,
        "language": selected_language,
    }


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


@app.post("/voice-ask")
async def voice_ask(
    audio: UploadFile = File(...),
    session_id: str = Form(default="default"),
    language: str | None = Form(default=None),
    preset_language: str | None = Form(default=None),
    lang_override: str | None = Form(default=None),
    debug: bool = Form(default=False),
):
    """
    Combined single-call endpoint: audio blob → full answer JSON.

    Pipeline:
      1. Language selection (from dropdown / form field)
      2. ASR with selected language (Faster-Whisper + VAD)
      3. English normalization (EuroLLM, skipped if selected_language == "en")
      4. Qdrant retrieval
      5. Answer generation in selected language
    """
    selected_language = normalize_language(language or preset_language or lang_override)
    audio_bytes = await audio.read()
    filename = audio.filename or "recording"
    content_type = audio.content_type or "unknown"
    size_bytes = len(audio_bytes) if audio_bytes else 0

    print(f"[voice-ask] Received '{filename}' ({content_type}, {size_bytes} bytes), lang={selected_language}")

    if not audio_bytes or size_bytes < 100:
        print(f"[voice-ask] Rejected: audio data empty or too small ({size_bytes} bytes)")
        raise HTTPException(status_code=400, detail="No audio data received or audio too small.")

    if size_bytes > MAX_AUDIO_BYTES:
        print(f"[voice-ask] Rejected: audio file exceeds limit ({size_bytes} bytes)")
        raise HTTPException(status_code=413, detail="Audio file too large.")

    try:
        asr_result = _asr_transcribe(audio_bytes, language=selected_language)
    except (av.error.InvalidDataError, av.error.FFmpegError, av.AVError, ValueError) as exc:
        print(f"[voice-ask] Audio decode error for '{filename}': {exc}")
        raise HTTPException(
            status_code=400,
            detail="Invalid or corrupted audio upload. Please record again.",
        )
    except Exception as exc:
        print(f"[voice-ask] Unexpected ASR failure for '{filename}': {exc}")
        raise HTTPException(
            status_code=500,
            detail="Speech recognition failed. Please try again.",
        )

    transcript = asr_result.get("transcript", "").strip()

    if not transcript:
        print(f"[voice-ask] Empty transcript returned for '{filename}'")
        raise HTTPException(
            status_code=422,
            detail="Could not transcribe audio. Please speak clearly and try again.",
        )

    print(f"[voice-ask] Transcribed: [{selected_language}] '{transcript}'")

    # Step 3: Normalize to English for retrieval
    if selected_language == "en":
        normalized_query_en = transcript
    else:
        normalized_query_en = normalize_to_english(
            transcript=transcript,
            detected_language=selected_language,
            language_confidence=1.0,
            tokenizer=tokenizer,
            model=llm,
            device=device,
        )

    # Step 4: Retrieve + Generate via /ask logic
    ask_body = AskRequest(
        question=transcript,
        session_id=session_id,
        debug=debug,
        language=selected_language,
        normalized_query_en=normalized_query_en,
        transcript=transcript,
    )

    # Reuse the /ask handler logic directly
    return await ask(ask_body)



# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
