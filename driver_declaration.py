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


def find_heading_index(
    lines: list[str],
    heading: str,
    start: int = 0,
) -> int | None:
    target = normalize_for_match(heading)

    for i in range(start, len(lines)):
        candidate = normalize_for_match(lines[i])

        if candidate == target:
            return i

    for i in range(start, len(lines)):
        candidate = normalize_for_match(lines[i])

        if target in candidate:
            return i

    for i in range(start, len(lines) - 1):
        combined = normalize_for_match(lines[i] + " " + lines[i + 1])

        if combined == target or target in combined:
            return i

    return None


CHUNK_METADATA = {
    "driver_declaration_intro": {
        "chunk_id": "driver_declaration_intro",
        "chunk_kind": "declaration",
        "section_title": "Driver Declaration",
        "subsection_title": "Confirmation of Information and Understanding",
        "topic_tags": [
            "driver_declaration",
            "confirmation",
            "understanding",
            "employment_responsibilities",
            "germany",
        ],
        "intent_type": "explanation",
        "entity_tags": [
            "EuroJobsCenter",
            "Germany",
            "EU Code 95",
            "Driver Card",
        ],
        "base_language": "en",
    },
    "declaration": {
        "chunk_id": "driver_declaration_statement",
        "chunk_kind": "declaration",
        "section_title": "Driver Declaration",
        "subsection_title": "Declaration",
        "topic_tags": [
            "declaration",
            "acknowledgement",
            "voluntary_confirmation",
            "professional_responsibility",
        ],
        "intent_type": "explanation",
        "entity_tags": [
            "EuroJobsCenter",
            "Germany",
        ],
        "base_language": "en",
    },
    "applicant_information": {
        "chunk_id": "driver_declaration_applicant_information",
        "chunk_kind": "checklist",
        "section_title": "Driver Declaration",
        "subsection_title": "Applicant Information",
        "topic_tags": [
            "applicant_information",
            "identity_details",
            "passport_number",
            "signature",
            "contact_details",
        ],
        "intent_type": "document_checklist",
        "entity_tags": [
            "passport",
        ],
        "base_language": "en",
    },
    "final_message": {
        "chunk_id": "driver_declaration_final_message",
        "chunk_kind": "message",
        "section_title": "Driver Declaration",
        "subsection_title": "Final Message",
        "topic_tags": [
            "final_message",
            "trust",
            "professional_support",
            "journey_to_germany",
            "career_start",
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

    # PDF pages 38–41 -> zero-based indices 37–40.
    for page_num in [37, 38, 39, 40]:
        raw_text += (reader.pages[page_num].extract_text() or "") + "\n"

    normalized = normalize_text(raw_text)
    all_lines = normalized.splitlines()
    lines = remove_footer(all_lines)

    markers = [
        ("driver_declaration_intro", "DRIVER DECLARATION"),
        ("declaration", "Declaration"),
        ("applicant_information", "Applicant Information"),
        ("final_message", "FINAL MESSAGE"),
    ]

    found = []
    search_start = 0

    for kind, heading in markers:
        index = find_heading_index(lines, heading, start=search_start)

        if index is not None:
            found.append((kind, index, heading))
            search_start = index + 1
        else:
            print(f"WARNING: heading not found -> {heading}")

    if not found:
        raise ValueError("No headings were found in the extracted text.")

    chunks = []

    for i, (kind, start_index, heading) in enumerate(found):
        if i + 1 < len(found):
            end_index = found[i + 1][1]
        else:
            end_index = len(lines)

        chunk_text = "\n".join(lines[start_index:end_index])
        chunks.append(make_chunk(kind, chunk_text))

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
        "output/driver_declaration.jsonl"
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
