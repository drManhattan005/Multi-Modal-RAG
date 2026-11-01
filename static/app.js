/**
 * app.js — Veloit Voice RAG frontend
 *
 * Client-side speech integration via useSpeech (Web Speech API):
 *   - STT (SpeechRecognition): interim transcripts shown live in input box,
 *     final transcript automatically sent via existing sendMessage().
 *   - TTS (speechSynthesis): optional auto-speaking of bot answers (speaker toggle,
 *     persisted in localStorage), stop-speaking control, and individual Recite buttons.
 *   - SSR-safe, gracefully disables mic/speaker if unsupported in browser.
 */

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------
const form             = document.getElementById("chat-form");
const input            = document.getElementById("message");
const chat             = document.getElementById("chat");
const statusEl         = document.getElementById("status");
const resetBtn         = document.getElementById("reset-btn");
const debugToggle      = document.getElementById("debug-toggle");
const micBtn           = document.getElementById("mic-btn");
const micPulse         = document.getElementById("mic-pulse");
const langOverride     = document.getElementById("lang-override");
const speakerToggleBtn = document.getElementById("speaker-toggle-btn");
const stopSpeakingBtn  = document.getElementById("stop-speaking-btn");

// Transcript panel (kept for backward compatibility if present)
const transcriptPanel   = document.getElementById("transcript-panel");
const transcriptText    = document.getElementById("transcript-text");
const transcriptDismiss = document.getElementById("transcript-dismiss");
const queryRow          = document.getElementById("query-row");
const normalizedQuery   = document.getElementById("normalized-query");

// Debug panel
const dbgStatus        = document.getElementById("dbg-status");
const dbgLang          = document.getElementById("dbg-lang");
const dbgQuery         = document.getElementById("dbg-query");
const dbgScore         = document.getElementById("dbg-score");
const dbgChunks        = document.getElementById("dbg-chunks");
const dbgHistory       = document.getElementById("dbg-history");
const dbgContext       = document.getElementById("dbg-context");
const dbgSession       = document.getElementById("dbg-session");
const debugChunksEl    = document.getElementById("debug-chunks");
const debugContextEl   = document.getElementById("debug-context");

// Non-blocking TTS notice toast
const ttsNoticeEl      = document.getElementById("tts-notice");

// Session ring
const ringProgress     = document.getElementById("ring-progress");
const ringLabel        = document.getElementById("ring-label");

// ---------------------------------------------------------------------------
// Constants & State
// ---------------------------------------------------------------------------
const SESSION_ID        = "default";
const RADIUS            = 22;
const CIRCUMFERENCE     = 2 * Math.PI * RADIUS;

if (ringProgress) {
  ringProgress.style.strokeDasharray  = `${CIRCUMFERENCE}`;
  ringProgress.style.strokeDashoffset = `${CIRCUMFERENCE}`;
}

// Language code → display name
const LANG_NAMES = {
  en: "English", de: "Deutsch", fr: "Français", es: "Español",
  it: "Italiano", nl: "Nederlands", pt: "Português", pl: "Polski",
  sv: "Svenska",  da: "Dansk",    fi: "Suomi",    nb: "Norsk",
  cs: "Čeština",  sk: "Slovenčina", hu: "Magyar", ro: "Română",
  bg: "Български", hr: "Hrvatski", el: "Ελληνικά", tr: "Türkçe",
};

// Language code → BCP-47 locale tag for STT/TTS (defaults to en-IN for English)
const BCP47_MAP = {
  en: "en-IN", de: "de-DE", fr: "fr-FR", es: "es-ES",
  it: "it-IT", pt: "pt-PT", nl: "nl-NL", pl: "pl-PL",
  sv: "sv-SE", da: "da-DK", fi: "fi-FI", nb: "nb-NO",
  cs: "cs-CZ", sk: "sk-SK", hu: "hu-HU", ro: "ro-RO",
  bg: "bg-BG", hr: "hr-HR", el: "el-GR", tr: "tr-TR",
};

let isProcessing        = false;
let isListening         = false;
let stopListeningFn     = null;
let activeSpeakingMsgId = null;
let ttsNoticeTimer      = null;

// Speaker toggle state (default OFF, persisted in localStorage)
let speakerEnabled = false;
try {
  speakerEnabled = localStorage.getItem("speaker_enabled") === "true";
} catch (_) {
  speakerEnabled = false;
}

// ---------------------------------------------------------------------------
// Toast Notice
// ---------------------------------------------------------------------------
function showTTSNotice(msg) {
  if (!ttsNoticeEl) return;
  ttsNoticeEl.textContent = msg;
  ttsNoticeEl.classList.remove("hidden");
  ttsNoticeEl.classList.add("visible");
  if (ttsNoticeTimer) clearTimeout(ttsNoticeTimer);
  ttsNoticeTimer = setTimeout(() => {
    ttsNoticeEl.classList.remove("visible");
    ttsNoticeEl.classList.add("hidden");
  }, 4000);
}

// ---------------------------------------------------------------------------
// Speaker (TTS) Toggle & Controls
// ---------------------------------------------------------------------------
function updateSpeakerToggleUI() {
  if (!speakerToggleBtn) return;
  if (!window.useSpeech || !window.useSpeech.ttsSupported) {
    speakerToggleBtn.style.display = "none";
    return;
  }
  speakerToggleBtn.style.display = "inline-flex";
  if (speakerEnabled) {
    speakerToggleBtn.classList.add("active");
    speakerToggleBtn.setAttribute("aria-pressed", "true");
    speakerToggleBtn.title = "Auto-speak replies (TTS is ON)";
  } else {
    speakerToggleBtn.classList.remove("active");
    speakerToggleBtn.setAttribute("aria-pressed", "false");
    speakerToggleBtn.title = "Auto-speak replies (TTS is OFF)";
  }
}

if (speakerToggleBtn) {
  speakerToggleBtn.addEventListener("click", () => {
    speakerEnabled = !speakerEnabled;
    try {
      localStorage.setItem("speaker_enabled", speakerEnabled ? "true" : "false");
    } catch (_) {}
    updateSpeakerToggleUI();
    if (!speakerEnabled && window.useSpeech) {
      window.useSpeech.stopSpeaking();
    }
  });
}

if (stopSpeakingBtn) {
  stopSpeakingBtn.addEventListener("click", () => {
    if (window.useSpeech) {
      window.useSpeech.stopSpeaking();
    }
  });
}

// Sync global speaking state to UI
if (window.useSpeech && typeof window.useSpeech.onSpeakingChange === "function") {
  window.useSpeech.onSpeakingChange((isSpeaking) => {
    if (stopSpeakingBtn) {
      if (isSpeaking) {
        stopSpeakingBtn.classList.remove("hidden");
      } else {
        stopSpeakingBtn.classList.add("hidden");
      }
    }
    if (!isSpeaking) {
      activeSpeakingMsgId = null;
      updateReciteButtons();
    }
  });
}

// ---------------------------------------------------------------------------
// UI Utilities
// ---------------------------------------------------------------------------
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function setStatus(msg) {
  if (statusEl) statusEl.textContent = msg;
}

function setInputsDisabled(disabled) {
  if (input) input.disabled = disabled;
  if (micBtn && window.useSpeech && window.useSpeech.sttSupported) {
    micBtn.disabled = disabled;
  }
  const submitBtn = form ? form.querySelector("[type='submit']") : null;
  if (submitBtn) submitBtn.disabled = disabled;
}

function setRing(fillRatio) {
  if (!ringProgress || !ringLabel) return;
  const ratio  = Math.max(0, Math.min(fillRatio || 0, 1));
  const offset = CIRCUMFERENCE * (1 - ratio);
  ringProgress.style.strokeDashoffset = `${offset}`;
  ringLabel.textContent = `${Math.round(ratio * 100)}%`;
  ringProgress.style.stroke =
    ratio < 0.5 ? "#22c55e" : ratio < 0.8 ? "#eab308" : "#ef4444";
}

// ---------------------------------------------------------------------------
// Chat messages & Recite buttons
// ---------------------------------------------------------------------------
function updateReciteButtons() {
  const buttons = document.querySelectorAll(".recite-btn");
  buttons.forEach((btn) => {
    const id = btn.getAttribute("data-msg-id");
    const isCurrent = (activeSpeakingMsgId !== null && activeSpeakingMsgId === id);
    if (isCurrent) {
      btn.classList.add("speaking");
      btn.setAttribute("aria-label", "Stop");
      btn.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg> Stop`;
    } else {
      btn.classList.remove("speaking");
      btn.setAttribute("aria-label", "Recite answer aloud");
      btn.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg> Recite`;
    }
  });
}

function addMessage(text, role, sources = [], meta = {}) {
  const msgId = "msg-" + Date.now() + "-" + Math.random().toString(36).slice(2, 7);
  const wrap = document.createElement("div");
  wrap.className = `message ${role}`;
  wrap.setAttribute("data-msg-id", msgId);
  wrap.setAttribute("data-lang", meta.language || "en");

  const textEl = document.createElement("div");
  textEl.className = "message-text";
  textEl.textContent = text;
  wrap.appendChild(textEl);

  // Recite button for bot replies
  if (role === "bot" && window.useSpeech && window.useSpeech.ttsSupported) {
    const actionsRow = document.createElement("div");
    actionsRow.className = "msg-actions-row";

    const reciteBtn = document.createElement("button");
    reciteBtn.type = "button";
    reciteBtn.className = "tts-btn recite-btn";
    reciteBtn.setAttribute("data-msg-id", msgId);
    reciteBtn.setAttribute("aria-label", "Recite answer aloud");
    reciteBtn.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg> Recite`;

    reciteBtn.addEventListener("click", () => {
      if (activeSpeakingMsgId === msgId) {
        window.useSpeech.stopSpeaking();
        activeSpeakingMsgId = null;
        updateReciteButtons();
      } else {
        const msgLang = wrap.getAttribute("data-lang") || langOverride.value || "en";
        const bcpTag = BCP47_MAP[msgLang] || msgLang || "en-IN";
        activeSpeakingMsgId = msgId;
        updateReciteButtons();
        window.useSpeech.speak(text, bcpTag, {
          onEnd: () => {
            activeSpeakingMsgId = null;
            updateReciteButtons();
          },
          onError: () => {
            activeSpeakingMsgId = null;
            updateReciteButtons();
          },
        });
      }
    });

    actionsRow.appendChild(reciteBtn);
    wrap.appendChild(actionsRow);
  }

  if (role === "bot" && sources && sources.length) {
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
  if (!dbgStatus) return;
  const meta  = data.meta  || {};
  const debug = data.debug || {};

  dbgStatus.textContent = "Last response";
  dbgLang.textContent   = data.language
    ? `${data.language} (${LANG_NAMES[data.language] || "?"})` : "–";
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
  if (debugChunksEl) {
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
  }

  if (debugContextEl) {
    debugContextEl.textContent = debug.context_preview || "Debug disabled.";
  }
}

// ---------------------------------------------------------------------------
// Response Renderer (handles auto-speak if enabled)
// ---------------------------------------------------------------------------
function renderResponse(data, userText) {
  removeTypingIndicator();

  const meta = {
    language: data.language,
  };

  addMessage(data.answer || "No answer returned.", "bot", data.sources || [], meta);
  renderDebug(data);

  // Auto-speak new bot reply if speaker toggle is ON
  if (speakerEnabled && data.answer && window.useSpeech && window.useSpeech.ttsSupported) {
    const langCode = data.language || langOverride.value || "en";
    const bcpTag = BCP47_MAP[langCode] || langCode || "en-IN";
    window.useSpeech.speak(data.answer, bcpTag);
  }
}

// ---------------------------------------------------------------------------
// Send message pipeline (shared by text enter & voice auto-send)
// ---------------------------------------------------------------------------
async function sendMessage() {
  if (isProcessing) return;

  // Stop STT listening if active
  if (isListening && stopListeningFn) {
    stopListeningFn();
    stopListeningFn = null;
  }
  resetListeningUI();

  const message = input.value.trim();
  if (!message) return;

  if (window.useSpeech) {
    window.useSpeech.stopSpeaking();
  }

  isProcessing = true;
  addMessage(message, "user");
  input.value = "";
  setInputsDisabled(true);
  setStatus("Thinking…");
  if (dbgStatus) dbgStatus.textContent = "Running";

  const typing = addTypingIndicator();

  try {
    const selectedLang = langOverride ? (langOverride.value || "en") : "en";
    const res = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: SESSION_ID,
        question:   message,
        debug:      debugToggle ? debugToggle.checked : false,
        language:   selectedLang,
      }),
    });

    const data = await res.json();

    if (!res.ok) {
      removeTypingIndicator();
      addMessage(data.detail || data.error || "Request failed.", "bot");
      setStatus("Error");
    } else {
      renderResponse(data, message);
    }
  } catch (err) {
    removeTypingIndicator();
    addMessage("Could not reach backend.", "bot");
    if (dbgStatus) dbgStatus.textContent = "Error";
    console.error(err);
  } finally {
    isProcessing = false;
    setInputsDisabled(false);
    if (input) input.focus();
    setStatus("Ready");
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  sendMessage();
});

// ---------------------------------------------------------------------------
// Client-side STT (SpeechRecognition)
// ---------------------------------------------------------------------------
function resetListeningUI() {
  isListening = false;
  if (micBtn) {
    micBtn.classList.remove("recording");
    micBtn.setAttribute("aria-pressed", "false");
  }
  if (micPulse) {
    micPulse.classList.remove("active");
  }
}

function initSTT() {
  if (!micBtn) return;

  if (!window.useSpeech || !window.useSpeech.sttSupported) {
    micBtn.disabled = true;
    micBtn.title = "Voice input not supported in this browser, try Chrome, Edge or Safari";
    micBtn.setAttribute(
      "aria-label",
      "Voice input not supported in this browser, try Chrome, Edge or Safari"
    );
    return;
  }

  micBtn.title = "Click to speak";
  micBtn.setAttribute("aria-label", "Start voice input");

  micBtn.addEventListener("click", () => {
    if (isProcessing) return;

    if (isListening) {
      // User clicked while listening -> stop
      if (stopListeningFn) {
        stopListeningFn();
        stopListeningFn = null;
      }
      resetListeningUI();
      setStatus("Ready");
      return;
    }

    // Start listening
    if (window.useSpeech) {
      window.useSpeech.stopSpeaking();
    }

    isListening = true;
    micBtn.classList.add("recording");
    micBtn.setAttribute("aria-pressed", "true");
    if (micPulse) micPulse.classList.add("active");
    setStatus("Listening… speak clearly");

    const selectedLang = langOverride ? (langOverride.value || "en") : "en";
    const bcpTag = BCP47_MAP[selectedLang] || selectedLang || "en-IN";

    stopListeningFn = window.useSpeech.listen(
      // onInterim: show live transcript in input box
      (interimText) => {
        if (input) {
          input.value = interimText;
        }
      },
      // onFinal: put final transcript in input box and auto-send via existing pipeline
      (finalText) => {
        resetListeningUI();
        stopListeningFn = null;
        if (finalText && finalText.trim()) {
          if (input) input.value = finalText.trim();
          sendMessage();
        }
      },
      bcpTag,
      {
        onStart: () => {
          setStatus("Listening… speak clearly");
        },
        onError: (err, type) => {
          resetListeningUI();
          stopListeningFn = null;
          showTTSNotice(err.message || "Speech recognition error.");
          setStatus("Ready");
        },
        onEnd: ({ hasSpeech }) => {
          resetListeningUI();
          stopListeningFn = null;
          if (!isProcessing) {
            setStatus("Ready");
          }
        },
      }
    );
  });
}

// ---------------------------------------------------------------------------
// Reset
// ---------------------------------------------------------------------------
async function resetSession() {
  if (window.useSpeech) {
    window.useSpeech.stopSpeaking();
  }
  if (isListening && stopListeningFn) {
    stopListeningFn();
    stopListeningFn = null;
    resetListeningUI();
  }

  try {
    await fetch("/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: SESSION_ID }),
    });
  } catch (_) {}

  chat.innerHTML = "";
  if (transcriptPanel) transcriptPanel.classList.add("hidden");
  if (debugChunksEl) debugChunksEl.innerHTML = `<div class="debug-empty">No request yet.</div>`;
  if (debugContextEl) debugContextEl.textContent = "No request yet.";
  if (dbgStatus)   dbgStatus.textContent   = "Reset";
  if (dbgLang)     dbgLang.textContent     = "–";
  if (dbgQuery)    dbgQuery.textContent    = "–";
  if (dbgScore)    dbgScore.textContent    = "–";
  if (dbgChunks)   dbgChunks.textContent   = "–";
  if (dbgHistory)  dbgHistory.textContent  = "–";
  if (dbgContext)  dbgContext.textContent  = "–";
  if (dbgSession)  dbgSession.textContent  = "–";
  setRing(0);
  setStatus("Ready");
}

if (resetBtn) {
  resetBtn.addEventListener("click", resetSession);
}

// ---------------------------------------------------------------------------
// Initialization
// ---------------------------------------------------------------------------
setRing(0);
if (debugChunksEl) debugChunksEl.innerHTML = `<div class="debug-empty">No request yet.</div>`;
updateSpeakerToggleUI();
initSTT();
