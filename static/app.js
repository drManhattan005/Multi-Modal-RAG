/**
 * app.js — Veloit Voice RAG frontend
 *
 * Two input paths:
 *   TEXT:  user types → POST /ask
 *   VOICE: user clicks mic → MediaRecorder → POST /voice-ask → renders result
 *
 * The voice path returns the same JSON shape as /ask, so the same
 * renderResponse() function handles both.
 */

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------
const form           = document.getElementById("chat-form");
const input          = document.getElementById("message");
const chat           = document.getElementById("chat");
const statusEl       = document.getElementById("status");
const resetBtn       = document.getElementById("reset-btn");
const debugToggle    = document.getElementById("debug-toggle");
const micBtn         = document.getElementById("mic-btn");
const micPulse       = document.getElementById("mic-pulse");
const langOverride   = document.getElementById("lang-override");

// Transcript panel
const transcriptPanel   = document.getElementById("transcript-panel");
const transcriptText    = document.getElementById("transcript-text");
const langBadge         = document.getElementById("lang-badge");
const langConfidence    = document.getElementById("lang-confidence");
const transcriptDismiss = document.getElementById("transcript-dismiss");
const queryRow          = document.getElementById("query-row");
const normalizedQuery   = document.getElementById("normalized-query");

// Debug panel
const dbgStatus   = document.getElementById("dbg-status");
const dbgLang     = document.getElementById("dbg-lang");
const dbgLangConf = document.getElementById("dbg-lang-conf");
const dbgQuery    = document.getElementById("dbg-query");
const dbgScore    = document.getElementById("dbg-score");
const dbgChunks   = document.getElementById("dbg-chunks");
const dbgHistory  = document.getElementById("dbg-history");
const dbgContext  = document.getElementById("dbg-context");
const dbgSession  = document.getElementById("dbg-session");
const debugChunksEl  = document.getElementById("debug-chunks");
const debugContextEl = document.getElementById("debug-context");

// Ring
const ringProgress = document.getElementById("ring-progress");
const ringLabel    = document.getElementById("ring-label");

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const SESSION_ID   = "default";
const RADIUS       = 22;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

ringProgress.style.strokeDasharray  = `${CIRCUMFERENCE}`;
ringProgress.style.strokeDashoffset = `${CIRCUMFERENCE}`;

// Language code → display name
const LANG_NAMES = {
  en: "English", de: "Deutsch", fr: "Français", es: "Español",
  it: "Italiano", nl: "Nederlands", pt: "Português", pl: "Polski",
  sv: "Svenska",  da: "Dansk",    fi: "Suomi",    cs: "Čeština",
  ro: "Română",   tr: "Türkçe",   el: "Ελληνικά", hu: "Magyar",
  sk: "Slovenčina", hr: "Hrvatski", bg: "Български",
};

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function setStatus(msg) {
  statusEl.textContent = msg;
}

function setInputsDisabled(disabled) {
  input.disabled  = disabled;
  micBtn.disabled = disabled;
  form.querySelector("[type='submit']").disabled = disabled;
}

// ---------------------------------------------------------------------------
// Ring indicator
// ---------------------------------------------------------------------------
function setRing(fillRatio) {
  const ratio  = Math.max(0, Math.min(fillRatio || 0, 1));
  const offset = CIRCUMFERENCE * (1 - ratio);
  ringProgress.style.strokeDashoffset = `${offset}`;
  ringLabel.textContent = `${Math.round(ratio * 100)}%`;
  ringProgress.style.stroke =
    ratio < 0.5 ? "#22c55e" : ratio < 0.8 ? "#eab308" : "#ef4444";
}

// ---------------------------------------------------------------------------
// Chat messages
// ---------------------------------------------------------------------------
function addMessage(text, role, sources = [], meta = {}) {
  const wrap = document.createElement("div");
  wrap.className = `message ${role}`;

  if (role === "voice") {
    // voice-initiated user bubble shows original transcript
    wrap.className = "message user voice-msg";
  }

  const textEl = document.createElement("div");
  textEl.className = "message-text";
  textEl.textContent = text;
  wrap.appendChild(textEl);

  // Language badge for bot messages
  if (role === "bot" && meta.detected_language && meta.detected_language !== "en") {
    const badge = document.createElement("span");
    badge.className = "msg-lang-badge";
    badge.textContent = LANG_NAMES[meta.detected_language] || meta.detected_language.toUpperCase();
    wrap.appendChild(badge);
  }

  if ((role === "bot" || role === "voice-bot") && sources.length) {
    const srcEl = document.createElement("div");
    srcEl.className = "sources";
    srcEl.textContent = "Sources: " + sources
      .filter(s => s.score >= 0.42)
      .map(s => `${s.section_title || "Unknown"} [${s.score}]`)
      .join(" · ");
    wrap.appendChild(srcEl);
  }

  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
  return wrap;
}

// Typing indicator
function addTypingIndicator() {
  const wrap = document.createElement("div");
  wrap.className = "message bot typing-msg";
  wrap.id = "typing-indicator";
  wrap.innerHTML = `<span class="dot"></span><span class="dot"></span><span class="dot"></span>`;
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
  return wrap;
}

function removeTypingIndicator() {
  const el = document.getElementById("typing-indicator");
  if (el) el.remove();
}

// ---------------------------------------------------------------------------
// Debug panel
// ---------------------------------------------------------------------------
function renderDebug(data) {
  const meta  = data.meta  || {};
  const debug = data.debug || {};

  dbgStatus.textContent = "Last response";
  dbgLang.textContent   = data.detected_language
    ? `${data.detected_language} (${LANG_NAMES[data.detected_language] || "?"})` : "–";
  dbgLangConf.textContent = data.language_confidence != null
    ? `${Math.round(data.language_confidence * 100)}%` : "–";
  dbgQuery.textContent  = data.normalized_query_en || "–";
  dbgScore.textContent  = meta.top_score   ?? "–";
  dbgChunks.textContent = meta.retrieved_chunks ?? "–";
  dbgHistory.textContent = meta.history_messages ?? "–";
  dbgContext.textContent = meta.context_chars_used && meta.context_char_limit
    ? `${meta.context_chars_used} / ${meta.context_char_limit}` : "–";
  dbgSession.textContent = meta.session_chars && meta.session_char_limit
    ? `${meta.session_chars} / ${meta.session_char_limit}` : "–";

  setRing(meta.session_fill_ratio || 0);

  const chunks = debug.retrieved_chunks || [];
  debugChunksEl.innerHTML = chunks.length
    ? chunks.map(c => `
        <div class="debug-item">
          <div class="debug-item-top">
            <strong>${escapeHtml(c.section_title || "Unknown")}</strong>
            <span class="score-pill">${c.score ?? "–"}</span>
          </div>
          <div class="debug-item-meta">${escapeHtml(c.source_file || "n/a")}</div>
          <div class="debug-item-preview">${escapeHtml(c.preview || "")}</div>
        </div>`).join("")
    : `<div class="debug-empty">Debug disabled or no chunks.</div>`;

  debugContextEl.textContent = debug.context_preview || "Debug disabled.";
}

// ---------------------------------------------------------------------------
// Transcript panel
// ---------------------------------------------------------------------------
function showTranscript(data) {
  transcriptText.textContent = data.transcript || "";
  const lang = data.detected_language || "?";
  langBadge.textContent = `${lang.toUpperCase()} – ${LANG_NAMES[lang] || lang}`;
  langBadge.className   = `lang-badge lang-${lang}`;
  const conf = data.language_confidence;
  langConfidence.textContent = conf != null ? `${Math.round(conf * 100)}% confidence` : "";

  if (data.normalized_query_en && data.normalized_query_en !== data.transcript) {
    normalizedQuery.textContent = data.normalized_query_en;
    queryRow.classList.remove("hidden");
  } else {
    queryRow.classList.add("hidden");
  }

  transcriptPanel.classList.remove("hidden");
  transcriptPanel.classList.add("slide-in");
}

transcriptDismiss.addEventListener("click", () => {
  transcriptPanel.classList.add("hidden");
  transcriptPanel.classList.remove("slide-in");
});

// ---------------------------------------------------------------------------
// Shared response renderer
// ---------------------------------------------------------------------------
function renderResponse(data, userText) {
  removeTypingIndicator();

  const meta = {
    detected_language:   data.detected_language,
    language_confidence: data.language_confidence,
  };

  addMessage(data.answer || "No answer returned.", "bot", data.sources || [], meta);
  renderDebug(data);
}

// ---------------------------------------------------------------------------
// TEXT submit flow
// ---------------------------------------------------------------------------
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (isProcessing || isRecording) return;
  const message = input.value.trim();
  if (!message) return;

  isProcessing = true;
  addMessage(message, "user");
  input.value = "";
  setInputsDisabled(true);
  setStatus("Thinking…");
  dbgStatus.textContent = "Running";

  const typing = addTypingIndicator();

  try {
    const res = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: SESSION_ID,
        question:   message,
        debug:      debugToggle.checked,
        target_language: langOverride.value || null,
      }),
    });

    const data = await res.json();

    if (!res.ok) {
      removeTypingIndicator();
      addMessage(data.detail || data.error || "Request failed.", "bot");
    } else {
      renderResponse(data, message);
    }
  } catch (err) {
    removeTypingIndicator();
    addMessage("Could not reach backend.", "bot");
    dbgStatus.textContent = "Error";
    console.error(err);
  } finally {
    isProcessing = false;
    setInputsDisabled(false);
    input.focus();
    setStatus("Ready");
  }
});

// ---------------------------------------------------------------------------
// VOICE recording flow
// ---------------------------------------------------------------------------
let mediaRecorder = null;
let audioChunks   = [];
let isRecording   = false;
let isProcessing  = false;
let micStream     = null;

function cleanupMedia() {
  if (micStream) {
    micStream.getTracks().forEach((t) => {
      try { t.stop(); } catch (_) {}
    });
    micStream = null;
  }
  mediaRecorder = null;
  audioChunks = [];
  isRecording = false;
}

async function startRecording() {
  if (isRecording || isProcessing) return;

  try {
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
  } catch (err) {
    console.error("Microphone access denied:", err);
    setStatus("Mic access denied");
    addMessage("Microphone permission denied. Please allow microphone access in your browser.", "bot");
    return;
  }

  // Guard against race conditions if state changed while awaiting user media
  if (isRecording || isProcessing) {
    cleanupMedia();
    return;
  }

  audioChunks = [];

  // Prefer webm/opus; fall back to supported browser formats
  let mimeType = "";
  if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
    mimeType = "audio/webm;codecs=opus";
  } else if (MediaRecorder.isTypeSupported("audio/webm")) {
    mimeType = "audio/webm";
  } else if (MediaRecorder.isTypeSupported("audio/ogg;codecs=opus")) {
    mimeType = "audio/ogg;codecs=opus";
  } else if (MediaRecorder.isTypeSupported("audio/mp4")) {
    mimeType = "audio/mp4";
  }

  try {
    mediaRecorder = new MediaRecorder(micStream, mimeType ? { mimeType } : {});
  } catch (err) {
    console.error("MediaRecorder initialization error:", err);
    cleanupMedia();
    setStatus("Mic error");
    addMessage("Could not start audio recorder. Please try again.", "bot");
    return;
  }

  mediaRecorder.ondataavailable = (e) => {
    if (e.data && e.data.size > 0) {
      audioChunks.push(e.data);
    }
  };

  mediaRecorder.onstop = handleRecordingStop;
  mediaRecorder.onerror = (e) => {
    console.error("MediaRecorder error:", e);
    stopRecording();
  };

  // Start recording without timeslice so the container header and metadata finalize cleanly on stop
  mediaRecorder.start();
  isRecording = true;

  micBtn.classList.add("recording");
  micBtn.setAttribute("aria-pressed", "true");
  micPulse.classList.add("active");
  setStatus("Recording… click again to stop");
}

async function stopRecording() {
  if (!isRecording || !mediaRecorder) return;
  isRecording = false;

  micBtn.classList.remove("recording");
  micBtn.setAttribute("aria-pressed", "false");
  micPulse.classList.remove("active");
  setStatus("Finishing recording…");

  try {
    if (mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
    }
  } catch (err) {
    console.error("Error stopping MediaRecorder:", err);
    cleanupMedia();
    setStatus("Ready");
  }
}

async function handleRecordingStop() {
  const mime = (mediaRecorder && mediaRecorder.mimeType) || "audio/webm";
  const recordedChunks = [...audioChunks];

  // Fully clean up mic stream and recorder references
  cleanupMedia();

  const blob = new Blob(recordedChunks, { type: mime });
  console.log(`[Voice] Audio recording finalized: size=${blob.size} bytes, mimeType=${blob.type || mime}`);

  // Reject empty or suspiciously tiny recordings (< 2 KB)
  if (!blob || blob.size < 2048) {
    console.warn(`[Voice] Rejected recording: ${blob ? blob.size : 0} bytes is under the 2 KB threshold.`);
    setStatus("Ready");
    setInputsDisabled(false);
    addMessage("Recording was too short or empty. Please speak clearly while recording.", "bot");
    return;
  }

  await sendVoiceBlob(blob, mime);
}

async function sendVoiceBlob(blob, mime = "audio/webm") {
  if (isProcessing) return;
  isProcessing = true;
  setInputsDisabled(true);
  setStatus("Transcribing & generating answer…");
  dbgStatus.textContent = "Transcribing + generating…";

  const extension = mime.includes("ogg")
    ? "recording.ogg"
    : mime.includes("mp4")
      ? "recording.mp4"
      : "recording.webm";

  const formData = new FormData();
  formData.append("audio",      blob,        extension);
  formData.append("session_id", SESSION_ID);
  formData.append("debug",      debugToggle.checked ? "true" : "false");
  if (langOverride.value) {
    formData.append("lang_override", langOverride.value);
  }

  const typing = addTypingIndicator();

  try {
    const res = await fetch("/voice-ask", {
      method: "POST",
      body: formData,
    });

    const data = await res.json();

    if (!res.ok) {
      removeTypingIndicator();
      addMessage(data.detail || "Voice request failed.", "bot");
      setStatus("Error");
      return;
    }

    // Show transcript panel with language info
    showTranscript(data);

    // Show user bubble with original transcript
    addMessage(data.transcript, "user");

    // Show answer
    renderResponse(data, data.transcript);

  } catch (err) {
    removeTypingIndicator();
    addMessage("Could not reach backend.", "bot");
    dbgStatus.textContent = "Error";
    console.error("Voice request error:", err);
  } finally {
    isProcessing = false;
    setInputsDisabled(false);
    input.focus();
    setStatus("Ready");
  }
}

// Toggle on click
micBtn.addEventListener("click", () => {
  if (isProcessing) return;
  if (isRecording) {
    stopRecording();
  } else {
    startRecording();
  }
});

// ---------------------------------------------------------------------------
// Reset
// ---------------------------------------------------------------------------
async function resetSession() {
  await fetch("/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: SESSION_ID }),
  });

  chat.innerHTML = "";
  transcriptPanel.classList.add("hidden");
  debugChunksEl.innerHTML = `<div class="debug-empty">No request yet.</div>`;
  debugContextEl.textContent = "No request yet.";
  dbgStatus.textContent   = "Reset";
  dbgLang.textContent     = "–";
  dbgLangConf.textContent = "–";
  dbgQuery.textContent    = "–";
  dbgScore.textContent    = "–";
  dbgChunks.textContent   = "–";
  dbgHistory.textContent  = "–";
  dbgContext.textContent  = "–";
  dbgSession.textContent  = "–";
  setRing(0);
  setStatus("Ready");
}

resetBtn.addEventListener("click", resetSession);

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
setRing(0);
debugChunksEl.innerHTML = `<div class="debug-empty">No request yet.</div>`;
