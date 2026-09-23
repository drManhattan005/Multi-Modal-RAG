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


def find_question_index(
    lines: list[str],
    question_number: int,
    start: int = 0,
) -> int | None:
    prefix = f"{question_number}."

    for i in range(start, len(lines)):
        candidate = normalize_for_match(lines[i])

        if not candidate.startswith(prefix):
            continue

        remainder = candidate[len(prefix):].strip()

        if remainder:
            return i

    return None


CHUNK_METADATA = {
    "faq_intro": {
        "chunk_id": "faq_intro",
        "chunk_kind": "intro",
        "section_title": "Frequently Asked Questions",
        "subsection_title": "Introduction",
        "topic_tags": [
            "faq",
            "introduction",
            "international_drivers",
            "germany",
            "truck_drivers",
        ],
        "intent_type": "explanation",
        "entity_tags": [
            "EuroJobsCenter",
            "Germany",
        ],
        "base_language": "en",
    },
    "final_message": {
        "chunk_id": "faq_final_message",
        "chunk_kind": "message",
        "section_title": "Frequently Asked Questions",
        "subsection_title": "Final Message",
        "topic_tags": [
            "final_message",
            "journey_to_germany",
            "career_start",
            "guidance",
            "support",
        ],
        "intent_type": "career_guidance",
        "entity_tags": [
            "EuroJobsCenter",
            "Germany",
        ],
        "base_language": "en",
    },
}


FAQ_METADATA = {
    1: {
        "subsection_title": "1. Why does Germany need professional truck drivers?",
        "topic_tags": ["driver_shortage", "germany", "transport", "logistics", "faq"],
        "intent_type": "faq",
        "entity_tags": ["Germany"],
    },
    2: {
        "subsection_title": "2. Is my job guaranteed?",
        "topic_tags": ["job_guarantee", "employment", "qualifications", "performance", "faq"],
        "intent_type": "faq",
        "entity_tags": [],
    },
    3: {
        "subsection_title": "3. Will my employer test my driving skills?",
        "topic_tags": ["driving_assessment", "skills_test", "employer", "safety", "faq"],
        "intent_type": "faq",
        "entity_tags": [],
    },
    4: {
        "subsection_title": "4. What happens if I fail the driving assessment?",
        "topic_tags": ["driving_assessment", "training", "employment_decision", "employer_procedure", "faq"],
        "intent_type": "faq",
        "entity_tags": [],
    },
    5: {
        "subsection_title": "5. Can I change employers later?",
        "topic_tags": ["changing_employers", "legal_requirements", "employment_change", "faq"],
        "intent_type": "faq",
        "entity_tags": ["Germany"],
    },
    6: {
        "subsection_title": "6. Do I have to leave Germany if my first job ends?",
        "topic_tags": ["job_end", "stay_in_germany", "legal_procedures", "employment_change", "faq"],
        "intent_type": "faq",
        "entity_tags": ["Germany"],
    },
    7: {
        "subsection_title": "7. Who decides whether I may change employers?",
        "topic_tags": ["authorities", "employment_change", "residence", "german_law", "faq"],
        "intent_type": "faq",
        "entity_tags": ["Germany", "German authorities"],
    },
    8: {
        "subsection_title": "8. Is Code 95 impossible to obtain?",
        "topic_tags": ["code95", "qualification", "international_drivers", "faq"],
        "intent_type": "faq",
        "entity_tags": ["Code 95"],
    },
    9: {
        "subsection_title": "9. Can I obtain a Driver Card?",
        "topic_tags": ["driver_card", "legal_requirements", "qualification", "faq"],
        "intent_type": "faq",
        "entity_tags": ["Driver Card"],
    },
    10: {
        "subsection_title": "10. Will someone help me with Code 95?",
        "topic_tags": ["code95", "training_support", "employer_support", "faq"],
        "intent_type": "faq",
        "entity_tags": ["Code 95", "EuroJobsCenter"],
    },
    11: {
        "subsection_title": "11. Will my employer help me after I arrive?",
        "topic_tags": ["arrival_support", "accommodation", "registration", "orientation", "faq"],
        "intent_type": "faq",
        "entity_tags": [],
    },
    12: {
        "subsection_title": "12. Will I receive accommodation?",
        "topic_tags": ["accommodation", "housing_support", "employer_support", "faq"],
        "intent_type": "faq",
        "entity_tags": [],
    },
    13: {
        "subsection_title": "13. Will I receive health insurance?",
        "topic_tags": ["health_insurance", "legal_employment", "germany", "faq"],
        "intent_type": "faq",
        "entity_tags": ["German health insurance system"],
    },
    14: {
        "subsection_title": "14. Will I pay taxes?",
        "topic_tags": ["taxes", "social_security", "employment", "germany", "faq"],
        "intent_type": "faq",
        "entity_tags": ["German law"],
    },
    15: {
        "subsection_title": "15. Can my salary increase?",
        "topic_tags": ["salary_increase", "experience", "performance", "qualifications", "faq"],
        "intent_type": "faq",
        "entity_tags": [],
    },
    16: {
        "subsection_title": "16. Can I receive bonuses?",
        "topic_tags": ["bonuses", "safe_driving", "attendance", "performance", "faq"],
        "intent_type": "faq",
        "entity_tags": [],
    },
    17: {
        "subsection_title": "17. Can I obtain additional qualifications?",
        "topic_tags": ["additional_qualifications", "adr", "tanker", "heavy_haulage", "faq"],
        "intent_type": "faq",
        "entity_tags": ["ADR"],
    },
    18: {
        "subsection_title": "18. Should I bring cash to Germany?",
        "topic_tags": ["cash", "arrival_expenses", "first_days", "germany", "faq"],
        "intent_type": "faq",
        "entity_tags": ["Germany"],
    },
    19: {
        "subsection_title": "19. Should I keep copies of my documents?",
        "topic_tags": ["document_copies", "passport", "visa", "driving_licence", "faq"],
        "intent_type": "faq",
        "entity_tags": ["passport", "visa", "driving licence"],
    },
    20: {
        "subsection_title": "20. What should I do if I do not understand something?",
        "topic_tags": ["ask_questions", "clarification", "legal_matters", "employment_matters", "faq"],
        "intent_type": "faq",
        "entity_tags": [],
    },
    21: {
        "subsection_title": "21. Can I contact EuroJobsCenter after arriving in Germany?",
        "topic_tags": ["eurojobscenter", "post_arrival_support", "guidance", "germany", "faq"],
        "intent_type": "faq",
        "entity_tags": ["EuroJobsCenter", "Germany"],
    },
    22: {
        "subsection_title": "22. Can someone pretend to represent EuroJobsCenter?",
        "topic_tags": ["fraud", "impersonation", "identity_verification", "scam_risk", "faq"],
        "intent_type": "faq",
        "entity_tags": ["EuroJobsCenter"],
    },
    23: {
        "subsection_title": "23. Should I pay money to private individuals?",
        "topic_tags": ["payments", "fraud_prevention", "official_payment_procedure", "faq"],
        "intent_type": "faq",
        "entity_tags": [],
    },
    24: {
        "subsection_title": "24. Why is the recruitment fee deposited with an escrow trustee?",
        "topic_tags": ["escrow", "recruitment_fee", "financial_security", "faq"],
        "intent_type": "faq",
        "entity_tags": ["escrow trustee", "EuroJobsCenter"],
    },
    25: {
        "subsection_title": "25. What happens if my visa is refused?",
        "topic_tags": ["visa_refusal", "escrow", "escrow_arrangement", "faq"],
        "intent_type": "faq",
        "entity_tags": ["visa", "escrow"],
    },
    26: {
        "subsection_title": "26. What should I do if I become ill?",
        "topic_tags": ["illness", "employer_reporting", "company_procedures", "faq"],
        "intent_type": "faq",
        "entity_tags": [],
    },
    27: {
        "subsection_title": "27. What is the most important quality of a professional driver?",
        "topic_tags": ["professionalism", "reliability", "honesty", "respect", "faq"],
        "intent_type": "faq",
        "entity_tags": [],
    },
    28: {
        "subsection_title": "28. How can I build a successful career in Germany?",
        "topic_tags": ["career_success", "safe_driving", "learning", "communication", "germany", "faq"],
        "intent_type": "faq",
        "entity_tags": ["Germany"],
    },
    29: {
        "subsection_title": "29. What should I do if I have doubts?",
        "topic_tags": ["doubts", "verify_information", "decision_making", "faq"],
        "intent_type": "faq",
        "entity_tags": [],
    },
    30: {
        "subsection_title": "30. What is EuroJobsCenter's most important advice?",
        "topic_tags": ["advice", "patience", "honesty", "professionalism", "career_guidance", "faq"],
        "intent_type": "faq",
        "entity_tags": ["EuroJobsCenter", "Germany"],
    },
}


def make_chunk(kind: str, text: str) -> dict:
    if kind.startswith("faq_") and kind != "faq_intro":
        question_number = int(kind.split("_")[1])
        faq_meta = FAQ_METADATA[question_number]

        return {
            "chunk_id": f"faq_{question_number}",
            "chunk_kind": "faq",
            "section_title": "Frequently Asked Questions",
            "subsection_title": faq_meta["subsection_title"],
            "topic_tags": faq_meta["topic_tags"],
            "intent_type": faq_meta["intent_type"],
            "entity_tags": faq_meta["entity_tags"],
            "base_language": "en",
            "text": text,
        }

    metadata = CHUNK_METADATA[kind].copy()
    metadata["text"] = text
    return metadata


def build_chunks(pdf_path: str) -> list[dict]:
    reader = PdfReader(pdf_path)

    raw_text = ""

    # PDF pages 32–37 -> zero-based indices 31–36.
    for page_num in [31, 32, 33, 34, 35, 36]:
        raw_text += (reader.pages[page_num].extract_text() or "") + "\n"

    normalized = normalize_text(raw_text)
    all_lines = normalized.splitlines()
    lines = remove_footer(all_lines)

    markers = [
        ("faq_intro", "FREQUENTLY ASKED QUESTIONS (FAQ)"),
    ]

    for question_number in range(1, 31):
        markers.append((f"faq_{question_number}", f"{question_number}."))

    markers.append(("final_message", "FINAL MESSAGE"))

    found = []
    search_start = 0

    for kind, heading in markers:
        if heading == "FINAL MESSAGE":
            index = find_heading_index(lines, heading, start=search_start)
        elif heading == "FREQUENTLY ASKED QUESTIONS (FAQ)":
            index = find_heading_index(lines, heading, start=search_start)
        else:
            index = find_question_index(
                lines,
                question_number=int(kind.split("_")[1]),
                start=search_start,
            )

        if index is not None:
            found.append((kind, index, heading))
            search_start = index + 1
        else:
            print(f"WARNING: heading not found -> {heading}")

    if not found:
        raise ValueError("No FAQ headings were found.")

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
        "output/faq.jsonl"
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
