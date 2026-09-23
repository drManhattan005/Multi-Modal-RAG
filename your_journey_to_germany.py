import json
from pathlib import Path

from pypdf import PdfReader


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00ad", "")
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(lines).strip()


def remove_footer(lines: list[str]) -> list[str]:
    footer_markers = [
        "EuroJobsCenter® - International Recruitment & Immigration Services - Germany",
        "Version 3.2 | August 2026",
        "Version 3.2 | August",
    ]

    result = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            continue

        if stripped in footer_markers:
            continue

        if stripped.isdigit():
            continue

        result.append(stripped)

    return result


def normalize_for_match(text: str) -> str:
    return " ".join(text.split()).strip().lower()


def find_line_index_contains(
    lines: list[str],
    needle: str,
    start: int = 0,
) -> int:
    target = normalize_for_match(needle)

    for i in range(start, len(lines)):
        candidate = normalize_for_match(lines[i])

        if candidate == target:
            return i

    for i in range(start, len(lines)):
        candidate = normalize_for_match(lines[i])

        if target in candidate:
            return i

    raise ValueError(f"Heading not found: {needle}")


def find_optional_line_index_contains(
    lines: list[str],
    needle: str,
    start: int = 0,
) -> int | None:
    target = normalize_for_match(needle)

    for i in range(start, len(lines)):
        candidate = normalize_for_match(lines[i])

        if candidate == target or target in candidate:
            return i

    return None


def find_step_index(
    lines: list[str],
    step_number: int,
    start: int = 0,
) -> int:
    target = f"step {step_number}"

    for i in range(start, len(lines)):
        candidate = normalize_for_match(lines[i])

        if candidate == target:
            return i

    for i in range(start, len(lines)):
        candidate = normalize_for_match(lines[i])

        if candidate.startswith(target):
            return i

    raise ValueError(f"Step heading not found: STEP {step_number}")


CHUNK_METADATA = {
    "journey_intro": {
        "chunk_id": "journey_intro",
        "chunk_kind": "intro",
        "section_title": "Your Journey to Germany",
        "subsection_title": "Introduction",
        "topic_tags": [
            "journey_to_germany",
            "travel_process",
            "arrival_preparation",
            "international_drivers",
            "germany",
        ],
        "intent_type": "arrival_guidance",
        "entity_tags": [
            "Germany",
            "EuroJobsCenter",
        ],
        "base_language": "en",
    },
    "step_1": {
        "chunk_id": "journey_step_1",
        "chunk_kind": "process_step",
        "section_title": "Your Journey to Germany",
        "subsection_title": "Step 1",
        "topic_tags": [
            "step_1",
            "journey_process",
            "travel_preparation",
            "germany",
        ],
        "intent_type": "process_step",
        "entity_tags": [
            "Germany",
        ],
        "base_language": "en",
    },
    "step_2": {
        "chunk_id": "journey_step_2",
        "chunk_kind": "process_step",
        "section_title": "Your Journey to Germany",
        "subsection_title": "Step 2",
        "topic_tags": [
            "step_2",
            "journey_process",
            "documentation",
            "travel_preparation",
        ],
        "intent_type": "process_step",
        "entity_tags": [],
        "base_language": "en",
    },
    "step_3": {
        "chunk_id": "journey_step_3",
        "chunk_kind": "process_step",
        "section_title": "Your Journey to Germany",
        "subsection_title": "Step 3",
        "topic_tags": [
            "step_3",
            "journey_process",
            "travel_documents",
            "pre_departure",
        ],
        "intent_type": "process_step",
        "entity_tags": [],
        "base_language": "en",
    },
    "step_4": {
        "chunk_id": "journey_step_4",
        "chunk_kind": "process_step",
        "section_title": "Your Journey to Germany",
        "subsection_title": "Step 4",
        "topic_tags": [
            "step_4",
            "journey_process",
            "visa_process",
            "departure_preparation",
        ],
        "intent_type": "process_step",
        "entity_tags": [
            "visa",
        ],
        "base_language": "en",
    },
    "step_5": {
        "chunk_id": "journey_step_5",
        "chunk_kind": "process_step",
        "section_title": "Your Journey to Germany",
        "subsection_title": "Step 5",
        "topic_tags": [
            "step_5",
            "journey_process",
            "travel_arrangements",
            "departure",
        ],
        "intent_type": "process_step",
        "entity_tags": [],
        "base_language": "en",
    },
    "step_6": {
        "chunk_id": "journey_step_6",
        "chunk_kind": "process_step",
        "section_title": "Your Journey to Germany",
        "subsection_title": "Step 6",
        "topic_tags": [
            "step_6",
            "journey_process",
            "travel_day",
            "arrival",
        ],
        "intent_type": "process_step",
        "entity_tags": [],
        "base_language": "en",
    },
    "step_7": {
        "chunk_id": "journey_step_7",
        "chunk_kind": "process_step",
        "section_title": "Your Journey to Germany",
        "subsection_title": "Step 7",
        "topic_tags": [
            "step_7",
            "journey_process",
            "arrival",
            "employer_contact",
        ],
        "intent_type": "process_step",
        "entity_tags": [],
        "base_language": "en",
    },
    "step_8": {
        "chunk_id": "journey_step_8",
        "chunk_kind": "process_step",
        "section_title": "Your Journey to Germany",
        "subsection_title": "Step 8",
        "topic_tags": [
            "step_8",
            "journey_process",
            "first_days",
            "administrative_steps",
        ],
        "intent_type": "process_step",
        "entity_tags": [],
        "base_language": "en",
    },
    "step_9": {
        "chunk_id": "journey_step_9",
        "chunk_kind": "process_step",
        "section_title": "Your Journey to Germany",
        "subsection_title": "Step 9",
        "topic_tags": [
            "step_9",
            "journey_process",
            "employment_start",
            "orientation",
        ],
        "intent_type": "process_step",
        "entity_tags": [],
        "base_language": "en",
    },
    "step_10": {
        "chunk_id": "journey_step_10",
        "chunk_kind": "process_step",
        "section_title": "Your Journey to Germany",
        "subsection_title": "Step 10",
        "topic_tags": [
            "step_10",
            "journey_process",
            "employment",
            "career_start",
            "germany",
        ],
        "intent_type": "process_step",
        "entity_tags": [
            "Germany",
        ],
        "base_language": "en",
    },
    "remember_summary": {
        "chunk_id": "journey_remember_summary",
        "chunk_kind": "summary",
        "section_title": "Your Journey to Germany",
        "subsection_title": "Remember",
        "topic_tags": [
            "summary",
            "journey_to_germany",
            "travel_preparation",
            "arrival",
            "germany",
        ],
        "intent_type": "explanation",
        "entity_tags": [
            "Germany",
        ],
        "base_language": "en",
    },
}


def make_chunk(kind: str, text: str) -> dict:
    metadata = CHUNK_METADATA[kind].copy()
    metadata["text"] = text
    return metadata


def build_chunks(pdf_path: str) -> list[dict]:
    reader = PdfReader(pdf_path)

    raw_text = ""

    # PDF pages 10, 11, 12, 13 -> zero-based indices 9, 10, 11, 12
    for page_num in [9, 10, 11, 12]:
        raw_text += (reader.pages[page_num].extract_text() or "") + "\n"

    normalized = normalize_text(raw_text)
    all_lines = normalized.splitlines()
    lines = remove_footer(all_lines)

    intro_heading_idx = find_line_index_contains(lines, "YOUR JOURNEY TO GERMANY")

    step_indices = []
    search_start = 0

    for step_number in range(1, 11):
        idx = find_step_index(lines, step_number, start=search_start)
        step_indices.append((f"step_{step_number}", idx))
        search_start = idx + 1

    chunks = []

    intro_lines = lines[intro_heading_idx:step_indices[0][1]]
    chunks.append(make_chunk("journey_intro", "\n".join(intro_lines)))

    for i, (kind, start_idx) in enumerate(step_indices[:-1]):
        end_idx = step_indices[i + 1][1]
        chunk_text = "\n".join(lines[start_idx:end_idx])
        chunks.append(make_chunk(kind, chunk_text))

    step_10_start = step_indices[-1][1]
    remember_idx = find_optional_line_index_contains(
        lines,
        "REMEMBER",
        start=step_10_start,
    )

    if remember_idx is not None:
        step_10_lines = lines[step_10_start:remember_idx]
        remember_lines = lines[remember_idx:]

        chunks.append(make_chunk("step_10", "\n".join(step_10_lines)))
        chunks.append(make_chunk("remember_summary", "\n".join(remember_lines)))
    else:
        step_10_lines = lines[step_10_start:]
        chunks.append(make_chunk("step_10", "\n".join(step_10_lines)))

    return chunks


def write_jsonl(chunks: list[dict], output_path: str) -> None:
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", encoding="utf-8") as file:
        for chunk in chunks:
            file.write(json.dumps(chunk, ensure_ascii=False) + "\n")


def main() -> None:
    pdf_path = (
        "/Users/hrugvedambre/Documents/Veloit-Voice-Rag/"
        "Visa & Immigration Handbook for Germany - 260807-1.pdf"
    )

    output_path = (
        "/Users/hrugvedambre/Documents/Veloit-Voice-Rag/"
        "output/your_journey_to_germany.jsonl"
    )

    chunks = build_chunks(pdf_path)
    write_jsonl(chunks, output_path)

    print(f"\nWrote {len(chunks)} chunks to: {output_path}")

    for chunk in chunks:
        print(f"\n--- CHUNK: {chunk['chunk_id']} ---\n")

        for key, value in chunk.items():
            if key == "text":
                continue

            print(f"{key}: {value}")

        print("\ntext:")
        print(chunk["text"])


if __name__ == "__main__":
    main()
