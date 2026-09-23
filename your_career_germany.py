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
    "career_intro": {
        "chunk_id": "career_intro",
        "chunk_kind": "intro",
        "section_title": "Your Career in Germany",
        "subsection_title": "Introduction",
        "topic_tags": [
            "career",
            "germany",
            "truck_drivers",
            "professional_future",
            "employment",
        ],
        "intent_type": "career_guidance",
        "entity_tags": [
            "Germany",
            "EuroJobsCenter",
        ],
        "base_language": "en",
    },
    "professionalism_creates_opportunities": {
        "chunk_id": "career_professionalism_creates_opportunities",
        "chunk_kind": "career_guidance",
        "section_title": "Your Career in Germany",
        "subsection_title": "Professionalism Creates Opportunities",
        "topic_tags": [
            "professionalism",
            "career_growth",
            "opportunities",
            "employability",
        ],
        "intent_type": "career_guidance",
        "entity_tags": [],
        "base_language": "en",
    },
    "your_salary": {
        "chunk_id": "career_your_salary",
        "chunk_kind": "explanation",
        "section_title": "Your Career in Germany",
        "subsection_title": "Your Salary",
        "topic_tags": [
            "salary",
            "employment_contract",
            "qualifications",
            "responsibilities",
            "earnings",
        ],
        "intent_type": "explanation",
        "entity_tags": [],
        "base_language": "en",
    },
    "bonuses_and_benefits": {
        "chunk_id": "career_bonuses_and_benefits",
        "chunk_kind": "explanation",
        "section_title": "Your Career in Germany",
        "subsection_title": "Bonuses and Additional Benefits",
        "topic_tags": [
            "bonuses",
            "benefits",
            "safe_driving",
            "attendance",
            "performance",
        ],
        "intent_type": "explanation",
        "entity_tags": [],
        "base_language": "en",
    },
    "paid_vacation": {
        "chunk_id": "career_paid_vacation",
        "chunk_kind": "legal_information",
        "section_title": "Your Career in Germany",
        "subsection_title": "Paid Vacation",
        "topic_tags": [
            "paid_vacation",
            "leave",
            "employment_rights",
            "germany",
        ],
        "intent_type": "legal_information",
        "entity_tags": [
            "Germany",
        ],
        "base_language": "en",
    },
    "health_insurance": {
        "chunk_id": "career_health_insurance",
        "chunk_kind": "legal_information",
        "section_title": "Your Career in Germany",
        "subsection_title": "Health Insurance",
        "topic_tags": [
            "health_insurance",
            "medical_coverage",
            "legal_employment",
            "germany",
        ],
        "intent_type": "legal_information",
        "entity_tags": [
            "Germany",
            "German health insurance system",
        ],
        "base_language": "en",
    },
    "social_security_pension": {
        "chunk_id": "career_social_security_pension",
        "chunk_kind": "legal_information",
        "section_title": "Your Career in Germany",
        "subsection_title": "Social Security and Pension",
        "topic_tags": [
            "social_security",
            "pension",
            "contributions",
            "employment_rights",
            "germany",
        ],
        "intent_type": "legal_information",
        "entity_tags": [
            "Germany",
        ],
        "base_language": "en",
    },
    "continuous_learning": {
        "chunk_id": "career_continuous_learning",
        "chunk_kind": "career_guidance",
        "section_title": "Your Career in Germany",
        "subsection_title": "Continuous Learning",
        "topic_tags": [
            "continuous_learning",
            "qualifications",
            "career_growth",
            "skills_development",
        ],
        "intent_type": "career_guidance",
        "entity_tags": [
            "Code 95",
            "Driver Card",
        ],
        "base_language": "en",
    },
    "respect_is_important": {
        "chunk_id": "career_respect_is_important",
        "chunk_kind": "career_guidance",
        "section_title": "Your Career in Germany",
        "subsection_title": "Respect Is Important",
        "topic_tags": [
            "respect",
            "professional_conduct",
            "workplace_behavior",
            "professionalism",
        ],
        "intent_type": "career_guidance",
        "entity_tags": [],
        "base_language": "en",
    },
    "your_reputation_matters": {
        "chunk_id": "career_your_reputation_matters",
        "chunk_kind": "career_guidance",
        "section_title": "Your Career in Germany",
        "subsection_title": "Your Reputation Matters",
        "topic_tags": [
            "reputation",
            "future_employers",
            "professionalism",
            "career_growth",
        ],
        "intent_type": "career_guidance",
        "entity_tags": [],
        "base_language": "en",
    },
    "long_term_journey": {
        "chunk_id": "career_long_term_journey",
        "chunk_kind": "summary",
        "section_title": "Your Career in Germany",
        "subsection_title": "Success Is a Long-Term Journey",
        "topic_tags": [
            "long_term_career",
            "success",
            "professional_growth",
            "career_development",
        ],
        "intent_type": "career_guidance",
        "entity_tags": [],
        "base_language": "en",
    },
    "our_message_to_you": {
        "chunk_id": "career_our_message_to_you",
        "chunk_kind": "message",
        "section_title": "Your Career in Germany",
        "subsection_title": "Our Message to You",
        "topic_tags": [
            "final_message",
            "career_guidance",
            "professionalism",
            "confidence",
            "germany",
        ],
        "intent_type": "career_guidance",
        "entity_tags": [
            "Germany",
            "EuroJobsCenter",
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
    for page_num in [17, 18, 19, 20, 21]:
        raw_text += (reader.pages[page_num].extract_text() or "") + "\n"

    normalized = normalize_text(raw_text)
    all_lines = normalized.splitlines()
    lines = remove_footer(all_lines)

    markers = [
        ("career_intro", "YOUR CAREER IN GERMANY"),
        ("professionalism_creates_opportunities", "Professionalism Creates Opportunities"),
        ("your_salary", "Your Salary"),
        ("bonuses_and_benefits", "Bonuses and Additional Benefits"),
        ("paid_vacation", "Paid Vacation"),
        ("health_insurance", "Health Insurance"),
        ("social_security_pension", "Social Security and Pension"),
        ("continuous_learning", "Continuous Learning"),
        ("respect_is_important", "Respect Is Important"),
        ("your_reputation_matters", "Your Reputation Matters"),
        ("long_term_journey", "Success Is a Long-Term Journey"),
        ("our_message_to_you", "OUR MESSAGE TO YOU"),
    ]

    found = []
    search_start = 0

    for kind, heading in markers:
        idx = find_heading_index(lines, heading, start=search_start)

        if idx is not None:
            found.append((kind, idx, heading))
            search_start = idx + 1
        else:
            print(f"WARNING: heading not found -> {heading}")

    if not found:
        raise ValueError("No headings were found in the extracted text.")

    chunks = []

    for i, (kind, start_idx, heading) in enumerate(found):
        if i + 1 < len(found):
            end_idx = found[i + 1][1]
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
        "output/your_career_germany.jsonl"
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
