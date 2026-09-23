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


def find_heading_index(lines: list[str], heading: str) -> int:
    target = " ".join(heading.split()).strip().lower()

    for i, line in enumerate(lines):
        candidate = " ".join(line.split()).strip().lower()
        if candidate == target:
            return i

    for i, line in enumerate(lines):
        candidate = " ".join(line.split()).strip().lower()
        if target in candidate:
            return i

    raise ValueError(f"Heading not found: {heading}")


CHUNK_METADATA = {
    "title_intro": {
        "chunk_id": "before_you_begin_title_intro",
        "chunk_kind": "intro",
        "section_title": "Before You Begin",
        "subsection_title": "Title and Introduction",
        "topic_tags": [
            "introduction",
            "career_start",
            "germany",
            "recruitment",
            "visa_process",
        ],
        "intent_type": "explanation",
        "entity_tags": [
            "EuroJobsCenter",
            "Germany",
        ],
        "base_language": "en",
    },
    "what_you_will_find": {
        "chunk_id": "before_you_begin_what_you_will_find",
        "chunk_kind": "summary",
        "section_title": "Before You Begin",
        "subsection_title": "What You Will Find in This Handbook",
        "topic_tags": [
            "handbook_overview",
            "fraud",
            "recruitment_process",
            "visa_procedure",
            "arrival",
            "career",
        ],
        "intent_type": "explanation",
        "entity_tags": [
            "EuroJobsCenter",
            "Germany",
            "Code 95",
            "Driver Card",
        ],
        "base_language": "en",
    },
    "our_promise": {
        "chunk_id": "before_you_begin_our_promise",
        "chunk_kind": "message",
        "section_title": "Before You Begin",
        "subsection_title": "Our Promise",
        "topic_tags": [
            "transparency",
            "professionalism",
            "trust",
            "career_guidance",
        ],
        "intent_type": "career_guidance",
        "entity_tags": [
            "EuroJobsCenter",
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
    for page_num in [1, 2]:
        raw_text += (reader.pages[page_num].extract_text() or "") + "\n"

    normalized = normalize_text(raw_text)
    all_lines = normalized.splitlines()
    lines = remove_footer(all_lines)

    handbook_idx = find_heading_index(lines, "WHAT YOU WILL FIND IN THIS HANDBOOK")
    promise_idx = find_heading_index(lines, "OUR PROMISE")

    intro_lines = lines[:handbook_idx]
    handbook_lines = lines[handbook_idx:promise_idx]
    promise_lines = lines[promise_idx:]

    return [
        make_chunk("title_intro", "\n".join(intro_lines)),
        make_chunk("what_you_will_find", "\n".join(handbook_lines)),
        make_chunk("our_promise", "\n".join(promise_lines)),
    ]


def write_jsonl(chunks: list[dict], output_path: str) -> None:
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")


def main() -> None:
    pdf_path = "/Users/hrugvedambre/Documents/Veloit-Voice-Rag/Visa & Immigration Handbook for Germany - 260807-1.pdf"
    output_path = "/Users/hrugvedambre/Documents/Veloit-Voice-Rag/output/before_you_begin.jsonl"

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
