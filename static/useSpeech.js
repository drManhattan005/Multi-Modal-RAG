/**
 * useSpeech.js — Client-side Web Speech API utility (STT & TTS)
 *
 * Provides browser-native SpeechRecognition (STT) and speechSynthesis (TTS).
 * SSR-safe: all `window` accesses are guarded for universal compatibility.
 */

(function (root, factory) {
  if (typeof define === "function" && define.amd) {
    define([], factory);
  } else if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.useSpeech = factory();
  }
})(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";

  // -------------------------------------------------------------------------
  // Feature detection (SSR-safe)
  // -------------------------------------------------------------------------
  const isBrowser = typeof window !== "undefined";

  const SpeechRecognitionClass = isBrowser
    ? window.SpeechRecognition || window.webkitSpeechRecognition || null
    : null;

  const sttSupported = Boolean(SpeechRecognitionClass);

  const ttsSupported = Boolean(
    isBrowser &&
      "speechSynthesis" in window &&
      "SpeechSynthesisUtterance" in window
  );

  // -------------------------------------------------------------------------
  // Voices cache & async loading
  // -------------------------------------------------------------------------
  let cachedVoices = [];

  function loadVoices() {
    if (!ttsSupported) return [];
    try {
      const list = window.speechSynthesis.getVoices() || [];
      if (list.length > 0) {
        cachedVoices = list;
      }
    } catch (_) {
      // Ignore errors in sandboxed environments
    }
    return cachedVoices;
  }

  if (ttsSupported) {
    loadVoices();
    if (typeof window.speechSynthesis.addEventListener === "function") {
      window.speechSynthesis.addEventListener("voiceschanged", () => {
        loadVoices();
      });
    } else if ("onvoiceschanged" in window.speechSynthesis) {
      window.speechSynthesis.onvoiceschanged = () => {
        loadVoices();
      };
    }
  }

  // -------------------------------------------------------------------------
  // Voice matching helper
  // -------------------------------------------------------------------------
  function findVoice(lang = "en-IN") {
    if (!ttsSupported) return null;
    const voices = cachedVoices.length ? cachedVoices : loadVoices();
    if (!voices || voices.length === 0) return null;

    const targetLang = (lang || "").toLowerCase().replace("_", "-");
    const targetPrefix = targetLang.split("-")[0];

    // 1. Exact match with localService
    let match = voices.find(
      (v) => v.lang && v.lang.toLowerCase() === targetLang && v.localService
    );
    if (match) return match;

    // 2. Exact match (any service)
    match = voices.find(
      (v) => v.lang && v.lang.toLowerCase() === targetLang
    );
    if (match) return match;

    // 3. Language-prefix match with localService
    match = voices.find(
      (v) =>
        v.lang &&
        v.lang.toLowerCase().split("-")[0] === targetPrefix &&
        v.localService
    );
    if (match) return match;

    // 4. Language-prefix match (any service)
    match = voices.find(
      (v) => v.lang && v.lang.toLowerCase().split("-")[0] === targetPrefix
    );
    if (match) return match;

    // 5. Default voice
    match = voices.find((v) => v.default);
    if (match) return match;

    // 6. First available voice
    return voices[0] || null;
  }

  // -------------------------------------------------------------------------
  // Text sanitization for TTS
  // Strips markdown symbols, code blocks, URLs, and citation markers like [1]
  // -------------------------------------------------------------------------
  function sanitizeText(text) {
    if (!text || typeof text !== "string") return "";

    let clean = text;

    // 1. Strip fenced code blocks ```...```
    clean = clean.replace(/```[\s\S]*?```/g, " ");

    // 2. Strip inline code `...`
    clean = clean.replace(/`([^`]+)`/g, "$1");

    // 3. Strip URLs
    clean = clean.replace(/https?:\/\/\S+/gi, " ");

    // 4. Strip markdown links [label](url) -> label
    clean = clean.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");

    // 5. Strip citation markers like [1], [2], [1, 2], [1-3]
    clean = clean.replace(/\[\s*\d+(?:\s*[,–-]\s*\d+)*\s*\]/g, " ");

    // 6. Strip trailing Sources: / Source: lines
    clean = clean.replace(/\n*\bSources?:[\s\S]*$/im, " ");

    // 7. Strip markdown header / blockquote / bullet symbols (*, #, _, >, ~, `)
    clean = clean.replace(/^[\s]*[#>*-]+ /gm, " ");
    clean = clean.replace(/[*_~`>#]/g, " ");

    // 8. Collapse whitespace
    clean = clean.replace(/\s+/g, " ").trim();

    return clean;
  }

  // -------------------------------------------------------------------------
  // Sentence chunking (approx 200 chars) to prevent Chrome utterance cutoff
  // -------------------------------------------------------------------------
  function splitIntoSentenceChunks(text, maxLen = 200) {
    if (!text) return [];

    // Split roughly by sentence boundaries (. ! ? or newline)
    const rawSegments = text.match(/[^.!?\n]+[.!?\n]*/g) || [text];
    const chunks = [];

    for (let seg of rawSegments) {
      seg = seg.trim();
      if (!seg) continue;

      if (seg.length <= maxLen) {
        chunks.push(seg);
      } else {
        // Break large segment by words
        const words = seg.split(" ");
        let current = "";
        for (const w of words) {
          if ((current + " " + w).trim().length <= maxLen) {
            current = (current + " " + w).trim();
          } else {
            if (current) chunks.push(current);
            current = w;
          }
        }
        if (current) chunks.push(current);
      }
    }

    return chunks;
  }

  // -------------------------------------------------------------------------
  // TTS State
  // -------------------------------------------------------------------------
  let currentSpeakSessionId = 0;
  let resumeTimer = null;
  let activeUtteranceCount = 0;
  let onSpeakingChangeListeners = new Set();

  function notifySpeakingState(isSpeaking) {
    onSpeakingChangeListeners.forEach((fn) => {
      try {
        fn(isSpeaking);
      } catch (err) {
        console.error("[useSpeech] listener error:", err);
      }
    });
  }

  function startResumeHeartbeat() {
    stopResumeHeartbeat();
    if (!isBrowser) return;
    // Chrome bug: SpeechSynthesis pauses after ~15s without active user gesture
    resumeTimer = setInterval(() => {
      if (
        isBrowser &&
        window.speechSynthesis &&
        window.speechSynthesis.speaking
      ) {
        window.speechSynthesis.resume();
      }
    }, 8000);
  }

  function stopResumeHeartbeat() {
    if (resumeTimer) {
      clearInterval(resumeTimer);
      resumeTimer = null;
    }
  }

  function stopSpeaking() {
    currentSpeakSessionId++;
    stopResumeHeartbeat();
    activeUtteranceCount = 0;

    if (ttsSupported && isBrowser && window.speechSynthesis) {
      try {
        window.speechSynthesis.cancel();
      } catch (err) {
        console.warn("[useSpeech] stopSpeaking error:", err);
      }
    }

    notifySpeakingState(false);
  }

  function speak(text, lang = "en-IN", options = {}) {
    if (!ttsSupported || !isBrowser || !window.speechSynthesis) {
      if (options.onError) {
        options.onError(new Error("Text-to-speech is not supported in this browser."));
      }
      return;
    }

    // Always cancel ongoing speech before starting new speech
    stopSpeaking();

    const sanitized = sanitizeText(text);
    if (!sanitized) return;

    const chunks = splitIntoSentenceChunks(sanitized, 200);
    if (!chunks.length) return;

    loadVoices();
    const voice = findVoice(lang);

    const sessionId = ++currentSpeakSessionId;
    activeUtteranceCount = chunks.length;
    notifySpeakingState(true);

    // Chrome drops utterances if queued synchronously with cancel(); wait 60ms
    setTimeout(() => {
      if (sessionId !== currentSpeakSessionId) return;

      startResumeHeartbeat();

      chunks.forEach((chunk, index) => {
        const utter = new SpeechSynthesisUtterance(chunk);
        utter.lang = lang;
        if (voice) {
          utter.voice = voice;
          if (voice.lang) utter.lang = voice.lang;
        }
        utter.rate = options.rate || 1.0;
        utter.pitch = options.pitch || 1.0;

        utter.onend = () => {
          if (sessionId !== currentSpeakSessionId) return;
          activeUtteranceCount--;
          if (activeUtteranceCount <= 0) {
            stopResumeHeartbeat();
            notifySpeakingState(false);
            if (options.onEnd) options.onEnd();
          }
        };

        utter.onerror = (e) => {
          if (sessionId !== currentSpeakSessionId) return;
          activeUtteranceCount--;
          if (e.error !== "canceled" && e.error !== "interrupted") {
            console.warn("[useSpeech] utterance error:", e.error);
            if (options.onError) options.onError(e);
          }
          if (activeUtteranceCount <= 0) {
            stopResumeHeartbeat();
            notifySpeakingState(false);
          }
        };

        window.speechSynthesis.speak(utter);
      });
    }, 60);
  }

  function onSpeakingChange(fn) {
    if (typeof fn === "function") {
      onSpeakingChangeListeners.add(fn);
    }
    return () => {
      onSpeakingChangeListeners.delete(fn);
    };
  }

  // -------------------------------------------------------------------------
  // STT: SpeechRecognition
  // -------------------------------------------------------------------------

  /**
   * Listen to user speech via Web Speech API.
   *
   * @param {Function} onInterim Callback for interim transcripts: (text: string) => void
   * @param {Function} onFinal Callback for final transcript: (text: string) => void
   * @param {string} lang BCP-47 language tag (default 'en-IN')
   * @param {Object} callbacks Additional error/lifecycle callbacks: { onError, onStart, onEnd }
   * @returns {Function} Stop listening function
   */
  function listen(onInterim, onFinal, lang = "en-IN", callbacks = {}) {
    if (!sttSupported || !SpeechRecognitionClass) {
      // TODO: Fallback with transformers.js / Whisper-in-browser for browsers without SpeechRecognition (e.g. Firefox)
      const errorMsg =
        "Voice input not supported in this browser, try Chrome, Edge or Safari";
      if (callbacks.onError) {
        callbacks.onError(new Error(errorMsg), "not-supported");
      }
      return () => {};
    }

    let recognition = null;
    let ended = false;
    let hasSpeech = false;

    try {
      recognition = new SpeechRecognitionClass();
    } catch (err) {
      if (callbacks.onError) callbacks.onError(err, "init-failed");
      return () => {};
    }

    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = lang || "en-IN";
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      if (callbacks.onStart) callbacks.onStart();
    };

    recognition.onresult = (event) => {
      let interimTranscript = "";
      let finalTranscript = "";

      for (let i = event.resultIndex; i < event.results.length; ++i) {
        const item = event.results[i];
        const transcriptChunk = item[0] ? item[0].transcript : "";
        if (item.isFinal) {
          finalTranscript += transcriptChunk;
        } else {
          interimTranscript += transcriptChunk;
        }
      }

      if (interimTranscript && typeof onInterim === "function") {
        hasSpeech = true;
        onInterim(interimTranscript);
      }

      if (finalTranscript && typeof onFinal === "function") {
        hasSpeech = true;
        onFinal(finalTranscript.trim());
      }
    };

    recognition.onerror = (event) => {
      let friendlyMessage = "Speech recognition error. Please try again.";
      const errorType = event.error;

      if (errorType === "not-allowed" || errorType === "service-not-allowed") {
        friendlyMessage =
          "Microphone permission denied. Please allow microphone access in your browser settings.";
      } else if (errorType === "no-speech") {
        friendlyMessage =
          "No speech detected. Please speak clearly into your microphone.";
      } else if (errorType === "audio-capture") {
        friendlyMessage =
          "No microphone was found. Ensure a microphone is installed and enabled.";
      } else if (errorType === "network") {
        friendlyMessage =
          "Network error during speech recognition. Please check your connection.";
      }

      if (callbacks.onError) {
        callbacks.onError(new Error(friendlyMessage), errorType);
      }
    };

    recognition.onend = () => {
      if (!ended) {
        ended = true;
        if (callbacks.onEnd) {
          callbacks.onEnd({ hasSpeech });
        }
      }
    };

    try {
      recognition.start();
    } catch (err) {
      ended = true;
      if (callbacks.onError) {
        callbacks.onError(err, "start-failed");
      }
      if (callbacks.onEnd) {
        callbacks.onEnd({ hasSpeech: false });
      }
    }

    // Return stop function
    return function stopListening() {
      if (recognition && !ended) {
        ended = true;
        try {
          recognition.stop();
        } catch (_) {}
      }
    };
  }

  // -------------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------------
  return {
    sttSupported,
    ttsSupported,
    listen,
    speak,
    stopSpeaking,
    sanitizeText,
    findVoice,
    onSpeakingChange,
  };
});
