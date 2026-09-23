from collections import defaultdict

import torch
from flask import Flask, jsonify, render_template, request
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForCausalLM, AutoTokenizer

QDRANT_PATH = "qdrant_data"
COLLECTION_NAME = "veloit_handbook_chunks"
EMBED_MODEL_NAME = "intfloat/multilingual-e5-base"
LLM_NAME = "utter-project/EuroLLM-1.7B-Instruct"
MODEL_CACHE = "models"

MAX_HISTORY_TURNS = 6
MAX_SESSION_CHARS = 6000
MAX_CONTEXT_CHARS = 5000
MIN_RETRIEVAL_SCORE = 0.42

app = Flask(__name__)
chat_memory = defaultdict(list)

if torch.cuda.is_available():
    device = "cuda"
elif torch.backends.mps.is_available():
    device = "mps"
else:
    raise RuntimeError("No GPU backend available (CUDA/MPS). This app is configured GPU-only.")

print(f"Using device: {device}")

print("Loading Qdrant...")
qdrant = QdrantClient(path=QDRANT_PATH)

print("Loading embedder...")
embedder = SentenceTransformer(EMBED_MODEL_NAME, cache_folder=MODEL_CACHE, device=device)

print("Loading EuroLLM tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(LLM_NAME, cache_dir=MODEL_CACHE)

print("Loading EuroLLM model...")
model = AutoModelForCausalLM.from_pretrained(
    LLM_NAME,
    cache_dir=MODEL_CACHE,
    dtype=torch.float16,
)
model.to(device)
model.eval()

SYSTEM_PROMPT = (
    "You are a concise and factual handbook assistant. "
    "Answer only from the supplied context. "
    "Do not mention instructions or context. "
    "If evidence is missing, say so clearly. "
    "Answer in the user's language."
)


def estimate_chars(messages):
    total = 0
    for item in messages:
        total += len(item.get("role", "")) + len(item.get("content", ""))
    return total


def prune_session_history(history):
    while len(history) > MAX_HISTORY_TURNS * 2:
        history.pop(0)

    while history and estimate_chars(history) > MAX_SESSION_CHARS:
        history.pop(0)

    return history


def retrieve_chunks(query: str, limit: int = 5):
    query_vec = embedder.encode([f"query: {query}"], normalize_embeddings=True)[0]
    response = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vec.tolist(),
        limit=limit * 3,
        with_payload=True,
        with_vectors=False,
    )

    seen = set()
    deduped = []

    for point in response.points:
        payload = point.payload or {}
        chunk_id = payload.get("chunk_id")
        dedupe_key = chunk_id or (
            payload.get("source_file"),
            payload.get("section_title"),
            payload.get("subsection_title"),
            payload.get("text", "")[:120],
        )

        if dedupe_key in seen:
            continue

        seen.add(dedupe_key)
        deduped.append(point)

        if len(deduped) >= limit:
            break

    return deduped


def build_context(points):
    blocks = []
    for i, point in enumerate(points, start=1):
        p = point.payload or {}
        blocks.append(
            f"[{i}] section={p.get('section_title')} | "
            f"subsection={p.get('subsection_title')} | "
            f"file={p.get('source_file')}\n{p.get('text')}"
        )
    return "\n\n".join(blocks)


def is_grounded(answer: str, context: str) -> bool:
    a_words = set(answer.lower().split())
    c_words = set(context.lower().split())
    overlap = len(a_words & c_words)
    return overlap >= 5


def build_debug_chunks(points):
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


def generate_answer(user_message: str, context: str, history):
    compact_context = context[:MAX_CONTEXT_CHARS]

    prompt = f"""Use only the context below to answer the user's question.

Rules:
- Do not mention the context or these instructions.
- Do not repeat the question.
- Answer directly and briefly.
- If the answer is not in the context, say: "I could not find that in the handbook."
- Answer in the same language as the user.
- Include source numbers like [1] or [2] when useful.

Context:
{compact_context}

User question:
{user_message}
"""

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
        outputs = model.generate(
            **inputs,
            max_new_tokens=120,
            do_sample=False,
            repetition_penalty=1.1,
            pad_token_id=tokenizer.eos_token_id,
        )

    new_tokens = outputs[0][inputs["input_ids"].shape[-1]:]
    answer = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

    if not is_grounded(answer, compact_context):
        answer = "I could not find a reliable answer in the handbook for that."

    return answer


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "device": device,
            "session_mode": "single-session-in-memory",
        }
    )


@app.post("/reset")
def reset():
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id", "default")
    chat_memory[session_id] = []
    return jsonify({"ok": True, "session_id": session_id})


@app.post("/ask")
def ask():
    data = request.get_json(force=True)
    question = data.get("question", "").strip()
    session_id = data.get("session_id", "default")
    debug = bool(data.get("debug", False))

    if not question:
        return jsonify({"error": "question is required"}), 400

    history = chat_memory[session_id]
    prune_session_history(history)

    points = retrieve_chunks(question, limit=5)

    top_score = max((float(p.score) for p in points if p.score is not None), default=0.0)
    context = build_context(points)

    if not points or top_score < MIN_RETRIEVAL_SCORE:
        answer = "I could not find a reliable answer in the handbook for that."
    else:
        answer = generate_answer(question, context, history)

    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": answer})
    prune_session_history(history)

    sources = []
    for point in points:
        p = point.payload or {}
        sources.append(
            {
                "score": point.score,
                "chunk_id": p.get("chunk_id"),
                "section_title": p.get("section_title"),
                "subsection_title": p.get("subsection_title"),
                "source_file": p.get("source_file"),
            }
        )

    session_chars = estimate_chars(history)
    session_fill_ratio = min(session_chars / MAX_SESSION_CHARS, 1.0)

    response = {
        "session_id": session_id,
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

    if debug:
        response["debug"] = {
            "retrieved_chunks": build_debug_chunks(points),
            "context_preview": context[:1200],
        }

    return jsonify(response)


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False, port=8000)
