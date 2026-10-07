"""
asr.py — ASR using faster-whisper loaded from local models/faster-whisper/.

No downloads. No network. Reads model files directly from disk.

ffmpeg must be installed on the system (brew install ffmpeg) so that
faster-whisper can decode browser audio (webm/ogg).
"""

from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

from faster_whisper import WhisperModel

# ---------------------------------------------------------------------------
# Load model from local directory — no HuggingFace, no network
# ---------------------------------------------------------------------------

_LOCAL_MODEL_DIR = str(Path(__file__).parent / "models" / "faster-whisper")

# CTranslate2 on CPU: int8_float32 provides better activation/layer-norm precision
# than pure int8 while maintaining fast CPU execution.
_DEVICE = "cpu"
_COMPUTE = "int8_float32"

print(f"[ASR] Loading faster-whisper from '{_LOCAL_MODEL_DIR}' ({_DEVICE} / {_COMPUTE})…")

_whisper = WhisperModel(
    _LOCAL_MODEL_DIR,
    device=_DEVICE,
    compute_type=_COMPUTE,
)

print("[ASR] faster-whisper ready.")


def _detect_audio_suffix(data: bytes) -> str:
    """Detect common audio container types by header magic bytes."""
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return ".webm"
    if data.startswith(b"OggS"):
        return ".ogg"
    if data.startswith(b"RIFF"):
        return ".wav"
    if len(data) >= 12 and (b"ftyp" in data[:16] or b"moov" in data[:16]):
        return ".mp4"
    return ".webm"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def transcribe(audio_bytes: bytes, lang_override: str | None = None) -> dict:
    """
    Returns {"transcript": str, "detected_language": str, "language_confidence": float}

    Requires ffmpeg on PATH to decode webm/ogg/mp4 audio from the browser.
    """
    if not audio_bytes or len(audio_bytes) < 100:
        raise ValueError("Audio payload is empty or too small.")

    suffix = _detect_audio_suffix(audio_bytes)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        # VAD parameters tuned to avoid cutting off natural conversational speech
        vad_parameters = {
            "threshold": 0.45,
            "min_speech_duration_ms": 200,
            "max_speech_duration_s": float("inf"),
            "min_silence_duration_ms": 1000,
            "speech_pad_ms": 400,
        }

        segments, info = _whisper.transcribe(
            tmp_path,
            language=lang_override or None,
            vad_filter=True,
            vad_parameters=vad_parameters,
            beam_size=5,
            best_of=5,
            temperature=0.0,
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
        )

        transcript = " ".join(seg.text for seg in segments).strip()

        # Fallback: if VAD filtered out soft/conversational speech, retry without VAD
        if not transcript:
            fallback_segments, fallback_info = _whisper.transcribe(
                tmp_path,
                language=lang_override or None,
                vad_filter=False,
                beam_size=5,
                temperature=0.0,
                condition_on_previous_text=False,
            )
            transcript = " ".join(seg.text for seg in fallback_segments).strip()
            if transcript:
                info = fallback_info

        detected = lang_override or (info.language if info else "en") or "en"
        confidence = (
            round(float(info.language_probability), 4)
            if info and info.language_probability is not None
            else 0.0
        )

        return {
            "transcript": transcript,
            "detected_language": detected,
            "language_confidence": confidence,
        }
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

