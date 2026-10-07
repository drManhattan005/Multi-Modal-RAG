"""
normalizer.py — Translate a non-English spoken query into a short English
retrieval query using the already-loaded EuroLLM.

This is intentionally a lightweight, fast call:
  - greedy decoding (temperature=0, do_sample=False)
  - max_new_tokens capped at 80
  - no chat history injected
  - skipped entirely when detected_language == "en"
"""

from __future__ import annotations

# These are imported lazily from app.py so they are only resolved at call time,
# avoiding circular imports.  Both references point to the module-level singletons.

_NORMALIZATION_PROMPT_TEMPLATE = (
    "You are a precise translation engine.\n"
    "Translate the following question into short, clear English suitable for document retrieval.\n"
    "Output ONLY the English translation, nothing else.\n\n"
    "Original ({lang}): {transcript}\n"
    "English:"
)

LOW_CONFIDENCE_THRESHOLD = 0.70  # fall back to original text as-is below this


def normalize_to_english(
    transcript: str,
    detected_language: str,
    language_confidence: float,
    tokenizer,
    model,
    device: str,
) -> str:
    """
    Return a short English version of *transcript* suitable for Qdrant retrieval.

    If the detected language is already English, or confidence is below the
    threshold, the original transcript is returned unchanged.

    Parameters
    ----------
    transcript:
        The raw transcribed text from Faster-Whisper.
    detected_language:
        ISO-639-1 language code returned by Whisper, e.g. "de".
    language_confidence:
        Whisper's probability for the detected language (0–1).
    tokenizer / model / device:
        The already-loaded EuroLLM instances (passed in from app.py to avoid
        circular imports and double-loading).
    """
    # Skip normalisation for English or low-confidence detections.
    if detected_language == "en":
        return transcript

    if language_confidence < LOW_CONFIDENCE_THRESHOLD:
        # Confidence is too low to trust the language detection — treat the
        # transcript as if it were English rather than risk a bad translation.
        return transcript

    if not model or not tokenizer:
        return transcript

    import re
    import torch  # local import to keep top of file clean

    prompt = _NORMALIZATION_PROMPT_TEMPLATE.format(
        lang=detected_language,
        transcript=transcript.strip(),
    )

    messages = [
        {"role": "system", "content": "You are a translation engine."},
        {"role": "user", "content": prompt},
    ]

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
            max_new_tokens=100,
            do_sample=False,
            temperature=1.0,       # ignored when do_sample=False
            repetition_penalty=1.0,
            pad_token_id=tokenizer.eos_token_id,
        )

    new_tokens = outputs[0][inputs["input_ids"].shape[-1]:]
    normalized = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

    # Clean up formatting artifacts (prefixes, surrounding quotes)
    normalized = re.sub(r"^(?:English|Translation|Translated query|Translated question):\s*", "", normalized, flags=re.IGNORECASE).strip()
    normalized = normalized.strip("\"' `")

    # Safety: if the model returns nothing useful or an error, fall back to original.
    if not normalized or len(normalized) < 2:
        return transcript

    return normalized
