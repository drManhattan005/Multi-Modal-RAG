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


def find_exact_heading_index(
    lines: list[str],
    heading: str,
    start: int = 0,
) -> int:
    target = normalize_for_match(heading)

    for i in range(start, len(lines)):
        candidate = normalize_for_match(lines[i])

        if candidate == target:
            return i

    raise ValueError(f"Heading not found (exact match required): {heading}")


CHUNK_METADATA = {
    "first_days_intro": {
        "chunk_id": "first_days_intro",
        "chunk_kind": "intro",
        "section_title": "Your First Days in Germany",
        "subsection_title": "Introduction",
        "topic_tags": [
            "arrival",
            "first_days",
            "germany",
            "orientation",
            "international_drivers",
        ],
        "intent_type": "arrival_guidance",
        "entity_tags": [
            "Germany",
            "EuroJobsCenter",
        ],
        "base_language": "en",
    },
    "your_arrival": {
        "chunk_id": "first_days_your_arrival",
        "chunk_kind": "process_step",
        "section_title": "Your First Days in Germany",
        "subsection_title": "Your Arrival",
        "topic_tags": [
            "arrival",
            "travel",
            "first_steps",
            "germany",
            "employer_contact",
        ],
        "intent_type": "arrival_guidance",
        "entity_tags": [
            "Germany",
        ],
        "base_language": "en",
    },
    "accommodation": {
        "chunk_id": "first_days_accommodation",
        "chunk_kind": "explanation",
        "section_title": "Your First Days in Germany",
        "subsection_title": "Accommodation",
        "topic_tags": [
            "accommodation",
            "housing",
            "temporary_housing",
            "employer_support",
        ],
        "intent_type": "arrival_guidance",
        "entity_tags": [],
        "base_language": "en",
    },
    "registration_administrative": {
        "chunk_id": "first_days_registration_administrative",
        "chunk_kind": "process_step",
        "section_title": "Your First Days in Germany",
        "subsection_title": "Registration and Administrative Procedures",
        "topic_tags": [
            "registration",
            "administrative_procedures",
            "documents",
            "legal_requirements",
            "germany",
        ],
        "intent_type": "process_step",
        "entity_tags": [
            "Germany",
        ],
        "base_language": "en",
    },
    "getting_to_know_employer": {
        "chunk_id": "first_days_getting_to_know_employer",
        "chunk_kind": "explanation",
        "section_title": "Your First Days in Germany",
        "subsection_title": "Getting to Know Your Employer",
        "topic_tags": [
            "employer",
            "company_orientation",
            "workplace_introduction",
            "first_days",
        ],
        "intent_type": "arrival_guidance",
        "entity_tags": [],
        "base_language": "en",
    },
    "practical_driving_assessment": {
        "chunk_id": "first_days_practical_driving_assessment",
        "chunk_kind": "process_step",
        "section_title": "Your First Days in Germany",
        "subsection_title": "Practical Driving Assessment",
        "topic_tags": [
            "driving_assessment",
            "skills_test",
            "safety",
            "employer_evaluation",
            "truck_drivers",
        ],
        "intent_type": "process_step",
        "entity_tags": [],
        "base_language": "en",
    },
    "communication_important": {
        "chunk_id": "first_days_communication_important",
        "chunk_kind": "explanation",
        "section_title": "Your First Days in Germany",
        "subsection_title": "Communication Is Important",
        "topic_tags": [
            "communication",
            "questions",
            "clarification",
            "professionalism",
            "first_days",
        ],
        "intent_type": "arrival_guidance",
        "entity_tags": [],
        "base_language": "en",
    },
    "first_impression_matters": {
        "chunk_id": "first_days_first_impression_matters",
        "chunk_kind": "career_guidance",
        "section_title": "Your First Days in Germany",
        "subsection_title": "Your First Impression Matters",
        "topic_tags": [
            "first_impression",
            "professionalism",
            "reliability",
            "respect",
            "career_start",
        ],
        "intent_type": "career_guidance",
        "entity_tags": [],
        "base_language": "en",
    },
    "remember_summary": {
        "chunk_id": "first_days_remember_summary",
        "chunk_kind": "summary",
        "section_title": "Your First Days in Germany",
        "subsection_title": "Remember",
        "topic_tags": [
            "summary",
            "first_days",
            "arrival",
            "professionalism",
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

    # PDF pages 14, 15, 16, 17 -> zero-based indices 13, 14, 15, 16
    for page_num in [13, 14, 15, 16]:
        raw_text += (reader.pages[page_num].extract_text() or "") + "\n"

    normalized = normalize_text(raw_text)
    all_lines = normalized.splitlines()
    lines = remove_footer(all_lines)

    markers = [
        ("first_days_intro", "YOUR FIRST DAYS IN GERMANY"),
        ("your_arrival", "Your Arrival"),
        ("accommodation", "Accommodation"),
        ("registration_administrative", "Registration and Administrative Procedures"),
        ("getting_to_know_employer", "Getting to Know Your Employer"),
        ("practical_driving_assessment", "Practical Driving Assessment"),
        ("communication_important", "Communication Is Important"),
        ("first_impression_matters", "Your First Impression Matters"),
        ("remember_summary", "Remember"),
    ]

    indices = []
    search_start = 0

    for kind, heading in markers:
        idx = find_exact_heading_index(lines, heading, start=search_start)
        indices.append((kind, idx))
        search_start = idx + 1

    chunks = []

    for i, (kind, start_idx) in enumerate(indices):
        if i + 1 < len(indices):
            end_idx = indices[i + 1][1]
        else:
            end_idx = len(lines)

        chunk_text = "\n".join(lines[start_idx:end_idx])
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
        "output/first_days_germany.jsonl"
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
