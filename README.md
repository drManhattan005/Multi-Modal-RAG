# Veloit Voice RAG

Multilingual handbook assistant for international truck drivers relocating to Germany, featuring client-side speech input/output (Web Speech API) and local Retrieval-Augmented Generation (RAG) powered by `qwen2.5:1.5b` via local Ollama.

---

## 1. Overview & Architecture

Veloit Voice RAG enables truck drivers to ask questions in any European language (via voice or text) and receive grounded, accurate answers referenced directly from the German Visa & Driver Handbook.

```
┌────────────────────────────────────────────────────────┐
│                   Browser (Client)                     │
│  - UI: Vanilla JS (static/app.js) & CSS                │
│  - Speech Input (STT): Web Speech API (useSpeech.js)  │
│  - Speech Output (TTS): Web Speech API Synthesis       │
└───────────────────────────┬────────────────────────────┘
                            │ HTTP POST /ask
                            ▼
┌────────────────────────────────────────────────────────┐
│                 FastAPI Backend (app.py)               │
│  - Embeddings: intfloat/multilingual-e5-base           │
│  - Vector Store: Local Qdrant (qdrant_data/)           │
└───────────────────────────┬────────────────────────────┘
                            │ HTTP POST /api/chat
                            ▼
┌────────────────────────────────────────────────────────┐
│             Local Ollama Server (localhost:11434)      │
│  - LLM Model: qwen2.5:1.5b                             │
└────────────────────────────────────────────────────────┘
```

- **Frontend**: Clean web UI served directly by FastAPI. Voice transcription (SpeechRecognition) and text-to-speech recitation (SpeechSynthesis) run entirely in the browser using the native Web Speech API. No server-side audio models are needed.
- **Backend**: FastAPI server (`app.py`) providing `/ask`, `/reset`, and `/health` endpoints.
- **Vector DB**: Embedded local Qdrant instance storing pre-indexed handbook text chunks in `qdrant_data/`.
- **Embeddings**: `intfloat/multilingual-e5-base` via `sentence-transformers`, generating dense embeddings for cross-lingual semantic search.
- **LLM**: Local `qwen2.5:1.5b` served via Ollama, generating concise, context-grounded answers under a ~2 GB CPU RAM budget.

---

## 2. Prerequisites

| Component | Required Version | Notes |
|---|---|---|
| **OS** | Windows 10/11, macOS 12+, or Linux (Ubuntu 20.04+) | Bare-metal setup (no Docker) |
| **Git** | 2.30+ | Required to clone repository |
| **Python** | **3.12** (3.10–3.12 supported) | Core runtime environment |
| **Node.js** | *None* | Frontend uses vanilla HTML/JS; no Node build step |
| **C++ Toolchain** | *None* | Pre-built binary wheels are installed for all packages |
| **OCR Tools** | *None* | Chunks are pre-extracted in `output/`; runtime needs no OCR |
| **Hardware** | Minimum 4 GB system RAM (~2 GB free for LLM), ~1 GB disk | Tuned for CPU execution |

---

## 3. Clone the Repository

```bash
git clone https://github.com/hrugvedambre/Veloit-Voice-Rag.git
cd Veloit-Voice-Rag
```

---

## 4. Backend Setup

### macOS / Linux

```bash
# 1. Create a Python 3.12 virtual environment
python3 -m venv .venv

# 2. Activate the virtual environment
source .venv/bin/activate

# 3. Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### Windows (PowerShell)

```powershell
# 1. Create a Python 3.12 virtual environment
python -m venv .venv

# 2. Activate the virtual environment
# Note: If script execution is restricted, run: Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.venv\Scripts\Activate.ps1

# 3. Upgrade pip and install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## 5. Frontend Setup

There is **no separate frontend installation or build step**. All frontend assets (`templates/index.html`, `static/app.js`, `static/useSpeech.js`, and `static/style.css`) are static files served directly by the FastAPI backend at `http://localhost:8000`.

---

## 6. Environment Variables

Create your local `.env` configuration file from `.env.example`:

**macOS / Linux:**
```bash
cp .env.example .env
```

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
```

### Configuration Options

| Variable | Description | Default |
|---|---|---|
| `OLLAMA_BASE_URL` | Base URL of the local Ollama instance | `http://localhost:11434` |
| `LLM_MODEL` | Ollama model identifier to use for generation | `qwen2.5:1.5b` |
| `LLM_NUM_CTX` | Context window size in tokens | `2048` |
| `LLM_NUM_THREAD` | Number of CPU worker threads allocated for Ollama | `4` |
| `LLM_TEMPERATURE` | Generation sampling temperature | `0.2` |
| `LLM_NUM_PREDICT` | Maximum new tokens generated per response | `512` |

---

## 7. Install and Prepare Ollama

1. **Download and Install Ollama**:
   - **macOS**: Download from [ollama.com/download/mac](https://ollama.com/download/mac)
   - **Windows**: Download from [ollama.com/download/windows](https://ollama.com/download/windows)
   - **Linux**: Run `curl -fsSL https://ollama.com/install.sh | sh`

2. **Verify Installation**:
   ```bash
   ollama --version
   ```

3. **Start the Ollama Server**:
   ```bash
   ollama serve
   ```
   *(Note: On macOS and Windows, starting the Ollama desktop application automatically runs the server in the background).*

4. **Pull `qwen2.5:1.5b`**:
   ```bash
   ollama pull qwen2.5:1.5b
   ```

5. **Verify the Model**:
   ```bash
   ollama list
   ```
   Quick inference test:
   ```bash
   ollama run qwen2.5:1.5b "hi"
   ```

6. **Check Memory Usage**:
   ```bash
   ollama ps
   ```
   `qwen2.5:1.5b` consumes roughly 1.0–1.2 GB of memory in 4-bit/default quantization.

---

## 8. Data Ingestion & Vector Indexing

The repository includes pre-extracted chunks from the official Germany Visa & Immigration Handbook in the `output/` directory.

To build and populate the local Qdrant vector database:

```bash
python ingest_qdrant.py
```

This script encodes the chunks using `intfloat/multilingual-e5-base` and stores vectors in `qdrant_data/`.

---

## 9. Run the Backend

Start the FastAPI application:

```bash
python app.py
```

Or run via Uvicorn directly:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

- **Web App**: [http://localhost:8000](http://localhost:8000)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)
- **Interactive API Docs (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)

On startup, the backend automatically verifies connectivity to Ollama and ensures `qwen2.5:1.5b` is available.

---

## 10. Open and Use the Web App

Open [http://localhost:8000](http://localhost:8000) in your web browser.

### Voice Support & Browser Caveats

1. **Secure Context Requirement**:
   The Web Speech API requires a secure context. It will only operate over `https://` or `http://localhost` / `http://127.0.0.1`.
2. **Browser Compatibility**:
   - **Chrome, Edge, Safari**: Full native support for speech recognition (STT) and voice synthesis (TTS).
   - **Firefox**: Voice synthesis (TTS) is supported. Speech recognition (STT) is not enabled by default in Firefox; type your queries into the chat box when using Firefox.
3. **Using Voice**:
   - Click the **🎙️ Mic button** to speak. The transcribed text will appear live in the input box and submit automatically upon silence.
   - Click the **Voice toggle** in the top navigation bar to enable automatic speech recitation of answers.
   - Click **Stop** at any time to cancel playback.

---

## 11. Smoke Test

To verify the pipeline via command line, execute a curl request against the `/ask` endpoint:

```bash
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is Code 95?"}'
```

### Expected Output Shape

```json
{
  "session_id": "default",
  "transcript": "What is Code 95?",
  "language": "en",
  "normalized_query_en": "What is Code 95?",
  "answer": "Code 95 is a mandatory professional driver qualification in the European Union required to work as a commercial truck driver...",
  "sources": [
    {
      "score": 0.8642,
      "chunk_id": "code95_overview",
      "section_title": "Code 95 & Driver Card",
      "subsection_title": "Overview",
      "source_file": "code95_driver_card.jsonl"
    }
  ],
  "meta": {
    "top_score": 0.8642,
    "retrieved_chunks": 3,
    "session_chars": 240,
    "session_char_limit": 10000,
    "session_fill_ratio": 0.024,
    "history_messages": 2,
    "context_chars_used": 1150,
    "context_char_limit": 4000
  }
}
```

---

## 12. Troubleshooting

| Issue | Cause | Resolution |
|---|---|---|
| `[ERROR] Could not connect to Ollama` / `Connection refused` | Ollama daemon is not running | Run `ollama serve` in a separate terminal or launch the Ollama desktop app. |
| `[ERROR] Model 'qwen2.5:1.5b' is not pulled` | Missing model weights | Execute `ollama pull qwen2.5:1.5b` and verify with `ollama list`. |
| Out of Memory (OOM) / System freeze | Context window or thread count too high for system RAM | In `.env`, lower `LLM_NUM_CTX=1024` and `LLM_NUM_THREAD=2`. |
| Slow CPU response | Ollama contending for CPU cores | Check CPU utilization; set `LLM_NUM_THREAD` in `.env` to match your physical core count (e.g., `4`). |
| `Address already in use` (Port 8000) | Another service or previous worker is using port 8000 | Stop the existing process: `lsof -i :8000` then `kill -9 <PID>` (macOS/Linux) or run on another port: `uvicorn app:app --port 8001`. |
| Microphone permission denied | Browser blocked microphone access | In browser address bar, click the site permissions lock icon and allow Microphone access. Verify running on `localhost` or `https://`. |
| `ModuleNotFoundError` on startup | Dependencies not installed in active environment | Ensure virtual environment is activated (`which python`), then run `pip install -r requirements.txt`. |

---

## 13. Project Structure

```
Veloit-Voice-Rag/
├── .env                  # Local runtime environment variables
├── .env.example          # Template environment configuration
├── app.py                # FastAPI server, lifespan health checks & RAG pipeline
├── ingest_qdrant.py      # Script to index handbook JSONL chunks into Qdrant
├── requirements.txt      # Python dependencies
├── templates/
│   └── index.html        # Web chat interface
├── static/
│   ├── app.js            # Frontend chat interactions & API communication
│   ├── useSpeech.js      # Client-side Web Speech API recognition & synthesis
│   └── style.css         # Styling and dark theme
├── output/               # Pre-extracted handbook JSONL text chunks
├── qdrant_data/          # Local Qdrant vector database storage
└── models/               # Cached embedding model weights
```
