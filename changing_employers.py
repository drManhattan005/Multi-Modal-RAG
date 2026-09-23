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
    "changing_employers_intro": {
        "chunk_id": "changing_employers_intro",
        "chunk_kind": "intro",
        "section_title": "Changing Employers in Germany",
        "subsection_title": "Introduction",
        "topic_tags": [
            "changing_employers",
            "career_mobility",
            "employment_change",
            "germany",
        ],
        "intent_type": "explanation",
        "entity_tags": [
            "Germany",
            "EuroJobsCenter",
        ],
        "base_language": "en",
    },
    "germany_needs_drivers": {
        "chunk_id": "changing_employers_germany_needs_drivers",
        "chunk_kind": "policy",
        "section_title": "Changing Employers in Germany",
        "subsection_title": "Germany Needs Professional Truck Drivers",
        "topic_tags": [
            "driver_shortage",
            "employment",
            "germany",
            "legal_employment",
        ],
        "intent_type": "legal_information",
        "entity_tags": [
            "Germany",
        ],
        "base_language": "en",
    },
    "employment_relationship_different": {
        "chunk_id": "changing_employers_employment_relationship_different",
        "chunk_kind": "explanation",
        "section_title": "Changing Employers in Germany",
        "subsection_title": "Every Employment Relationship Is Different",
        "topic_tags": [
            "employment_relationship",
            "career_change",
            "job_fit",
            "professional_life",
        ],
        "intent_type": "explanation",
        "entity_tags": [
            "Germany",
        ],
        "base_language": "en",
    },
    "example_better_offer": {
        "chunk_id": "changing_employers_example_better_offer",
        "chunk_kind": "summary",
        "section_title": "Changing Employers in Germany",
        "subsection_title": "Example",
        "topic_tags": [
            "better_job_offer",
            "berlin",
            "stuttgart",
            "changing_employers",
        ],
        "intent_type": "career_guidance",
        "entity_tags": [
            "Germany",
            "Stuttgart",
            "Berlin",
        ],
        "base_language": "en",
    },
    "example_employer_loses_work": {
        "chunk_id": "changing_employers_example_employer_loses_work",
        "chunk_kind": "summary",
        "section_title": "Changing Employers in Germany",
        "subsection_title": "Another Example",
        "topic_tags": [
            "employer_loses_work",
            "job_continuity",
            "employment_change",
            "legal_procedures",
        ],
        "intent_type": "career_guidance",
        "entity_tags": [
            "Germany",
        ],
        "base_language": "en",
    },
    "follow_legal_process": {
        "chunk_id": "changing_employers_follow_legal_process",
        "chunk_kind": "process_step",
        "section_title": "Changing Employers in Germany",
        "subsection_title": "Always Follow the Legal Process",
        "topic_tags": [
            "legal_process",
            "immigration_authority",
            "employment_change",
            "compliance",
        ],
        "intent_type": "process_step",
        "entity_tags": [
            "Germany",
            "EuroJobsCenter",
            "immigration authority",
        ],
        "base_language": "en",
    },
    "germany_offers_opportunities": {
        "chunk_id": "changing_employers_germany_offers_opportunities",
        "chunk_kind": "explanation",
        "section_title": "Changing Employers in Germany",
        "subsection_title": "Germany Offers Many Opportunities",
        "topic_tags": [
            "transport_companies",
            "career_growth",
            "employment_options",
            "germany",
        ],
        "intent_type": "career_guidance",
        "entity_tags": [
            "Germany",
        ],
        "base_language": "en",
    },
    "professional_reputation": {
        "chunk_id": "changing_employers_professional_reputation",
        "chunk_kind": "policy",
        "section_title": "Changing Employers in Germany",
        "subsection_title": "Your Reputation Is Your Greatest Asset",
        "topic_tags": [
            "reputation",
            "professionalism",
            "career_growth",
            "future_employers",
        ],
        "intent_type": "career_guidance",
        "entity_tags": [
            "Germany",
        ],
        "base_language": "en",
    },
    "remember_summary": {
        "chunk_id": "changing_employers_remember_summary",
        "chunk_kind": "summary",
        "section_title": "Changing Employers in Germany",
        "subsection_title": "Remember",
        "topic_tags": [
            "summary",
            "legal_employment",
            "professionalism",
            "career_change",
        ],
        "intent_type": "explanation",
        "entity_tags": [
            "Germany",
        ],
        "base_language": "en",
    },
    "our_message": {
        "chunk_id": "changing_employers_our_message",
        "chunk_kind": "message",
        "section_title": "Changing Employers in Germany",
        "subsection_title": "Our Message",
        "topic_tags": [
            "career_guidance",
            "law",
            "professional_conduct",
            "long_term_career",
        ],
        "intent_type": "career_guidance",
        "entity_tags": [
            "Germany",
        ],
        "base_language": "en",
    },
    "good_to_know": {
        "chunk_id": "changing_employers_good_to_know",
        "chunk_kind": "summary",
        "section_title": "Changing Employers in Germany",
        "subsection_title": "Good to Know",
        "topic_tags": [
            "example",
            "changing_employers",
            "legal_requirements",
            "qualified_professionals",
        ],
        "intent_type": "legal_information",
        "entity_tags": [
            "Germany",
            "Stuttgart",
            "Berlin",
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

    for page_num in [27, 28, 29, 30]:
        raw_text += (reader.pages[page_num].extract_text() or "") + "\n"

    normalized = normalize_text(raw_text)
    all_lines = normalized.splitlines()
    lines = remove_footer(all_lines)

    markers = [
        ("changing_employers_intro", "CHANGING EMPLOYERS IN GERMANY"),
        ("germany_needs_drivers", "Germany Needs Professional Truck Drivers"),
        ("employment_relationship_different", "Every Employment Relationship Is Different"),
        ("example_better_offer", "Example"),
        ("example_employer_loses_work", "Another Example"),
        ("follow_legal_process", "Always Follow the Legal Process"),
        ("germany_offers_opportunities", "Germany Offers Many Opportunities"),
        ("professional_reputation", "Your Reputation Is Your Greatest Asset"),
        ("remember_summary", "Remember"),
        ("our_message", "OUR MESSAGE"),
        ("good_to_know", "GOOD TO KNOW"),
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
        raise ValueError("No chunk headings were found.")

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

    with output_file.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")


def main() -> None:
    pdf_path = "/Users/hrugvedambre/Documents/Veloit-Voice-Rag/Visa & Immigration Handbook for Germany - 260807-1.pdf"
    output_path = "/Users/hrugvedambre/Documents/Veloit-Voice-Rag/output/changing_employers.jsonl"

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
