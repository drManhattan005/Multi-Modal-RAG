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


def normalize_for_match(text: str) -> str:
    return " ".join(text.split()).strip().lower()


def find_heading_index(lines: list[str], heading: str) -> int:
    target = normalize_for_match(heading)

    for i, line in enumerate(lines):
        candidate = normalize_for_match(line)

        if candidate == target:
            return i

    for i, line in enumerate(lines):
        candidate = normalize_for_match(line)

        if target in candidate:
            return i

    raise ValueError(f"Heading not found: {heading}")


CHUNK_METADATA = {
    "page_title_intro": {
        "chunk_id": "security_notice_page_title_intro",
        "chunk_kind": "intro",
        "section_title": "Important Security Notice",
        "subsection_title": "Introduction",
        "topic_tags": [
            "security_notice",
            "fraud_prevention",
            "payments",
            "document_safety",
            "recruitment",
        ],
        "intent_type": "warning",
        "entity_tags": [
            "EuroJobsCenter",
        ],
        "base_language": "en",
    },
    "security_notice_1": {
        "chunk_id": "security_notice_1",
        "chunk_kind": "warning",
        "section_title": "Important Security Notice",
        "subsection_title": "1. EuroJobsCenter Does Not Normally Accept Advance Payments",
        "topic_tags": [
            "advance_payments",
            "fraud_prevention",
            "payment_policy",
            "security_notice",
        ],
        "intent_type": "warning",
        "entity_tags": [
            "EuroJobsCenter",
        ],
        "base_language": "en",
    },
    "security_notice_2": {
        "chunk_id": "security_notice_2",
        "chunk_kind": "warning",
        "section_title": "Important Security Notice",
        "subsection_title": "2. Official Immigration Authority Fee (EUR 411)",
        "topic_tags": [
            "immigration_fee",
            "official_fee",
            "eur_411",
            "payment_verification",
            "security_notice",
        ],
        "intent_type": "warning",
        "entity_tags": [
            "immigration authority",
            "EUR 411",
        ],
        "base_language": "en",
    },
    "security_notice_3": {
        "chunk_id": "security_notice_3",
        "chunk_kind": "warning",
        "section_title": "Important Security Notice",
        "subsection_title": "3. Secure Escrow (Trustee) Payment System",
        "topic_tags": [
            "escrow",
            "trustee_payment",
            "payment_security",
            "recruitment_fee",
            "security_notice",
        ],
        "intent_type": "warning",
        "entity_tags": [
            "EuroJobsCenter",
            "escrow trustee",
        ],
        "base_language": "en",
    },
    "security_notice_4": {
        "chunk_id": "security_notice_4",
        "chunk_kind": "warning",
        "section_title": "Important Security Notice",
        "subsection_title": "4. Never Send Money to Unknown Persons",
        "topic_tags": [
            "fraud",
            "unknown_persons",
            "money_transfer",
            "payment_scam",
            "security_notice",
        ],
        "intent_type": "warning",
        "entity_tags": [],
        "base_language": "en",
    },
    "security_notice_5": {
        "chunk_id": "security_notice_5",
        "chunk_kind": "warning",
        "section_title": "Important Security Notice",
        "subsection_title": "5. Do Not Trust Logos, Stamps or Signatures Alone",
        "topic_tags": [
            "forged_documents",
            "verification",
            "logos",
            "stamps",
            "signatures",
            "security_notice",
        ],
        "intent_type": "warning",
        "entity_tags": [],
        "base_language": "en",
    },
    "security_notice_6": {
        "chunk_id": "security_notice_6",
        "chunk_kind": "warning",
        "section_title": "Important Security Notice",
        "subsection_title": "6. Never Feel Pressured to Pay Immediately",
        "topic_tags": [
            "pressure_tactics",
            "payment_pressure",
            "fraud_prevention",
            "security_notice",
        ],
        "intent_type": "warning",
        "entity_tags": [],
        "base_language": "en",
    },
    "security_notice_7": {
        "chunk_id": "security_notice_7",
        "chunk_kind": "warning",
        "section_title": "Important Security Notice",
        "subsection_title": "7. Protect Your Personal Documents",
        "topic_tags": [
            "personal_documents",
            "passport_safety",
            "identity_protection",
            "document_security",
            "security_notice",
        ],
        "intent_type": "warning",
        "entity_tags": [
            "passport",
        ],
        "base_language": "en",
    },
    "remember_summary": {
        "chunk_id": "security_notice_remember_summary",
        "chunk_kind": "summary",
        "section_title": "Important Security Notice",
        "subsection_title": "Remember",
        "topic_tags": [
            "summary",
            "fraud_prevention",
            "payment_security",
            "document_safety",
            "security_notice",
        ],
        "intent_type": "warning",
        "entity_tags": [
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
    for page_num in [3, 4, 5]:
        raw_text += (reader.pages[page_num].extract_text() or "") + "\n"

    normalized = normalize_text(raw_text)
    all_lines = normalized.splitlines()
    lines = remove_footer(all_lines)

    markers = [
        ("security_notice_1", "1. EuroJobsCenter Does Not Normally Accept Advance Payments"),
        ("security_notice_2", "2. Official Immigration Authority Fee (EUR 411)"),
        ("security_notice_3", "3. Secure Escrow (Trustee) Payment System"),
        ("security_notice_4", "4. Never Send Money to Unknown Persons"),
        ("security_notice_5", "5. Do Not Trust Logos, Stamps or Signatures Alone"),
        ("security_notice_6", "6. Never Feel Pressured to Pay Immediately"),
        ("security_notice_7", "7. Protect Your Personal Documents"),
        ("remember_summary", "Remember"),
    ]

    indices = []
    for kind, heading in markers:
        idx = find_heading_index(lines, heading)
        indices.append((kind, heading, idx))

    chunks = []

    first_idx = indices[0][2]
    intro_lines = lines[:first_idx]
    chunks.append(make_chunk("page_title_intro", "\n".join(intro_lines)))

    for i, (kind, heading, start_idx) in enumerate(indices):
        end_idx = indices[i + 1][2] if i + 1 < len(indices) else len(lines)
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
        "output/important_security_notice.jsonl"
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
