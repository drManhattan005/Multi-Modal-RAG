const form = document.getElementById("chat-form");
const input = document.getElementById("message");
const chat = document.getElementById("chat");
const statusEl = document.getElementById("status");
const resetBtn = document.getElementById("reset-btn");
const debugToggle = document.getElementById("debug-toggle");

const dbgStatus = document.getElementById("dbg-status");
const dbgScore = document.getElementById("dbg-score");
const dbgChunks = document.getElementById("dbg-chunks");
const dbgHistory = document.getElementById("dbg-history");
const dbgContext = document.getElementById("dbg-context");
const dbgSession = document.getElementById("dbg-session");
const debugChunksEl = document.getElementById("debug-chunks");
const debugContextEl = document.getElementById("debug-context");

const ringProgress = document.getElementById("ring-progress");
const ringLabel = document.getElementById("ring-label");

const sessionId = "default";
const RADIUS = 22;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

ringProgress.style.strokeDasharray = `${CIRCUMFERENCE}`;
ringProgress.style.strokeDashoffset = `${CIRCUMFERENCE}`;

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function addMessage(text, role, sources = []) {
    const wrap = document.createElement("div");
    wrap.className = `message ${role}`;

    const textEl = document.createElement("div");
    textEl.textContent = text;
    wrap.appendChild(textEl);

    if (role === "bot" && sources.length) {
        const meta = document.createElement("div");
        meta.className = "sources";
        meta.textContent = "Sources: " + sources
            .map(s => `${s.section_title || "Unknown"} (${s.source_file || "n/a"})`)
            .join(" • ");
        wrap.appendChild(meta);
    }

    chat.appendChild(wrap);
    chat.scrollTop = chat.scrollHeight;
}

function setRing(fillRatio) {
    const ratio = Math.max(0, Math.min(fillRatio || 0, 1));
    const offset = CIRCUMFERENCE * (1 - ratio);
    ringProgress.style.strokeDashoffset = `${offset}`;
    ringLabel.textContent = `${Math.round(ratio * 100)}%`;

    if (ratio < 0.5) {
        ringProgress.style.stroke = "#22c55e";
    } else if (ratio < 0.8) {
        ringProgress.style.stroke = "#eab308";
    } else {
        ringProgress.style.stroke = "#ef4444";
    }
}

function renderDebug(data) {
    const meta = data.meta || {};
    const debug = data.debug || {};

    dbgStatus.textContent = "Last response";
    dbgScore.textContent = meta.top_score ?? "-";
    dbgChunks.textContent = meta.retrieved_chunks ?? "-";
    dbgHistory.textContent = meta.history_messages ?? "-";
    dbgContext.textContent = meta.context_chars_used && meta.context_char_limit
        ? `${meta.context_chars_used} / ${meta.context_char_limit}`
        : "-";
    dbgSession.textContent = meta.session_chars && meta.session_char_limit
        ? `${meta.session_chars} / ${meta.session_char_limit}`
        : "-";

    setRing(meta.session_fill_ratio || 0);

    const chunks = debug.retrieved_chunks || [];
    if (!chunks.length) {
        debugChunksEl.innerHTML = `<div class="debug-empty">Debug disabled or no chunks returned.</div>`;
    } else {
        debugChunksEl.innerHTML = chunks.map(chunk => `
      <div class="debug-item">
        <div class="debug-item-top">
          <strong>${escapeHtml(chunk.section_title || "Unknown")}</strong>
          <span>${chunk.score ?? "-"}</span>
        </div>
        <div class="debug-item-meta">
          ${escapeHtml(chunk.source_file || "n/a")}
        </div>
        <div class="debug-item-preview">
          ${escapeHtml(chunk.preview || "")}
        </div>
      </div>
    `).join("");
    }

    debugContextEl.textContent = debug.context_preview || "Debug disabled.";
}

async function resetSession() {
    await fetch("/reset", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ session_id: sessionId })
    });

    chat.innerHTML = "";
    debugChunksEl.innerHTML = `<div class="debug-empty">No request yet.</div>`;
    debugContextEl.textContent = "No request yet.";
    dbgStatus.textContent = "Reset";
    dbgScore.textContent = "-";
    dbgChunks.textContent = "-";
    dbgHistory.textContent = "-";
    dbgContext.textContent = "-";
    dbgSession.textContent = "-";
    setRing(0);
    statusEl.textContent = "Ready";
}

form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const message = input.value.trim();
    if (!message) return;

    addMessage(message, "user");
    input.value = "";
    input.disabled = true;
    statusEl.textContent = "Thinking...";
    dbgStatus.textContent = "Running";

    try {
        const res = await fetch("/ask", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                session_id: sessionId,
                question: message,
                debug: debugToggle.checked
            })
        });

        const data = await res.json();

        if (!res.ok) {
            addMessage(data.error || "Request failed.", "bot");
        } else {
            addMessage(data.answer || "No answer returned.", "bot", data.sources || []);
            renderDebug(data);
        }
    } catch (err) {
        addMessage("Could not reach backend.", "bot");
        dbgStatus.textContent = "Error";
    } finally {
        input.disabled = false;
        input.focus();
        statusEl.textContent = "Ready";
    }
});

resetBtn.addEventListener("click", resetSession);

setRing(0);
debugChunksEl.innerHTML = `<div class="debug-empty">No request yet.</div>`;
