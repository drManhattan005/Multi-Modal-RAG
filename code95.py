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
    "code95_intro": {
        "chunk_id": "code95_driver_card_intro",
        "chunk_kind": "intro",
        "section_title": "EU Code 95 & Driver Card",
        "subsection_title": "Introduction",
        "topic_tags": [
            "code95",
            "driver_card",
            "professional_qualification",
            "truck_drivers",
            "germany",
        ],
        "intent_type": "explanation",
        "entity_tags": [
            "EU Code 95",
            "Driver Card",
            "Germany",
        ],
        "base_language": "en",
    },
    "what_is_code95": {
        "chunk_id": "code95_what_is_code95",
        "chunk_kind": "explanation",
        "section_title": "EU Code 95 & Driver Card",
        "subsection_title": "What Is the EU Code 95 Qualification?",
        "topic_tags": [
            "code95",
            "professional_qualification",
            "driver_training",
            "truck_driving",
            "european_union",
        ],
        "intent_type": "explanation",
        "entity_tags": [
            "EU Code 95",
            "European Union",
        ],
        "base_language": "en",
    },
    "international_drivers_code95": {
        "chunk_id": "code95_international_drivers",
        "chunk_kind": "legal_information",
        "section_title": "EU Code 95 & Driver Card",
        "subsection_title": "Can International Drivers Obtain Code 95?",
        "topic_tags": [
            "code95",
            "international_drivers",
            "qualification_process",
            "legal_requirements",
            "germany",
        ],
        "intent_type": "legal_information",
        "entity_tags": [
            "EU Code 95",
            "Germany",
        ],
        "base_language": "en",
    },
    "do_not_be_afraid": {
        "chunk_id": "code95_do_not_be_afraid",
        "chunk_kind": "message",
        "section_title": "EU Code 95 & Driver Card",
        "subsection_title": "Do Not Be Afraid",
        "topic_tags": [
            "code95",
            "reassurance",
            "training",
            "professional_development",
            "international_drivers",
        ],
        "intent_type": "career_guidance",
        "entity_tags": [
            "EU Code 95",
        ],
        "base_language": "en",
    },
    "what_is_driver_card": {
        "chunk_id": "code95_what_is_driver_card",
        "chunk_kind": "explanation",
        "section_title": "EU Code 95 & Driver Card",
        "subsection_title": "What Is the Driver Card?",
        "topic_tags": [
            "driver_card",
            "digital_tachograph",
            "driving_records",
            "truck_drivers",
        ],
        "intent_type": "explanation",
        "entity_tags": [
            "Driver Card",
            "digital tachograph",
        ],
        "base_language": "en",
    },
    "why_driver_card_important": {
        "chunk_id": "code95_why_driver_card_important",
        "chunk_kind": "legal_information",
        "section_title": "EU Code 95 & Driver Card",
        "subsection_title": "Why Is the Driver Card Important?",
        "topic_tags": [
            "driver_card",
            "legal_compliance",
            "driving_hours",
            "rest_periods",
            "road_safety",
        ],
        "intent_type": "legal_information",
        "entity_tags": [
            "Driver Card",
            "digital tachograph",
        ],
        "base_language": "en",
    },
    "support_during_process": {
        "chunk_id": "code95_support_during_process",
        "chunk_kind": "process_step",
        "section_title": "EU Code 95 & Driver Card",
        "subsection_title": "Support During the Process",
        "topic_tags": [
            "code95",
            "driver_card",
            "training_support",
            "employer_support",
            "qualification_process",
        ],
        "intent_type": "process_step",
        "entity_tags": [
            "EU Code 95",
            "Driver Card",
            "EuroJobsCenter",
        ],
        "base_language": "en",
    },
    "building_qualifications": {
        "chunk_id": "code95_building_qualifications",
        "chunk_kind": "career_guidance",
        "section_title": "EU Code 95 & Driver Card",
        "subsection_title": "Building Your Professional Qualifications",
        "topic_tags": [
            "professional_qualifications",
            "career_growth",
            "code95",
            "driver_card",
            "additional_training",
        ],
        "intent_type": "career_guidance",
        "entity_tags": [
            "EU Code 95",
            "Driver Card",
        ],
        "base_language": "en",
    },
    "remember_summary": {
        "chunk_id": "code95_remember_summary",
        "chunk_kind": "summary",
        "section_title": "EU Code 95 & Driver Card",
        "subsection_title": "Remember",
        "topic_tags": [
            "code95",
            "driver_card",
            "summary",
            "legal_compliance",
            "professional_development",
        ],
        "intent_type": "explanation",
        "entity_tags": [
            "EU Code 95",
            "Driver Card",
        ],
        "base_language": "en",
    },
    "our_message": {
        "chunk_id": "code95_our_message",
        "chunk_kind": "message",
        "section_title": "EU Code 95 & Driver Card",
        "subsection_title": "Our Message",
        "topic_tags": [
            "code95",
            "driver_card",
            "career_confidence",
            "professionalism",
            "training",
        ],
        "intent_type": "career_guidance",
        "entity_tags": [
            "EU Code 95",
            "Driver Card",
            "Germany",
        ],
        "base_language": "en",
    },
    "recommended_training_partner": {
        "chunk_id": "code95_recommended_training_partner",
        "chunk_kind": "partner_information",
        "section_title": "EU Code 95 & Driver Card",
        "subsection_title": "Recommended Training Partner for Code 95",
        "topic_tags": [
            "code95",
            "training_provider",
            "professional_training",
            "driver_qualification",
        ],
        "intent_type": "process_step",
        "entity_tags": [
            "EU Code 95",
            "training partner",
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

    # PDF pages 23–27 -> zero-based indices 22–26.
    for page_num in [22, 23, 24, 25, 26]:
        raw_text += (reader.pages[page_num].extract_text() or "") + "\n"

    normalized = normalize_text(raw_text)
    all_lines = normalized.splitlines()
    lines = remove_footer(all_lines)

    markers = [
        ("code95_intro", "EU CODE 95 & DRIVER CARD"),
        ("what_is_code95", "What Is the EU Code 95 Qualification?"),
        (
            "international_drivers_code95",
            "Can International Drivers Obtain Code 95?",
        ),
        ("do_not_be_afraid", "Do Not Be Afraid"),
        ("what_is_driver_card", "What Is the Driver Card?"),
        ("why_driver_card_important", "Why Is the Driver Card Important?"),
        ("support_during_process", "Support During the Process"),
        (
            "building_qualifications",
            "Building Your Professional Qualifications",
        ),
        ("remember_summary", "Remember"),
        ("our_message", "OUR MESSAGE"),
        (
            "recommended_training_partner",
            "Recommended Training Partner for Code 95",
        ),
    ]

    found = []
    search_start = 0

    for kind, heading in markers:
        index = find_heading_index(
            lines,
            heading,
            start=search_start,
        )

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
            file.write(
                json.dumps(
                    chunk,
                    ensure_ascii=False,
                )
                + "\n"
            )


def main() -> None:
    pdf_path = (
        "/Users/hrugvedambre/Documents/Veloit-Voice-Rag/"
        "Visa & Immigration Handbook for Germany - 260807-1.pdf"
    )

    output_path = (
        "/Users/hrugvedambre/Documents/Veloit-Voice-Rag/"
        "output/code95_driver_card.jsonl"
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
