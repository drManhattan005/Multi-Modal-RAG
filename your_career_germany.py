from dataclasses import dataclass
from pypdf import PdfReader


@dataclass(frozen=True)
class Chunk:
    kind: str
    text: str


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


def find_heading_index(lines: list[str], heading: str, start: int = 0) -> int | None:
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


def build_chunks(pdf_path: str) -> list[Chunk]:
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

        chunk_lines = lines[start_idx:end_idx]
        chunks.append(Chunk(kind=kind, text="\n".join(chunk_lines)))

    return chunks


def main() -> None:
    chunks = build_chunks(
        "/Users/hrugvedambre/Documents/Veloit-Voice-Rag/Visa & Immigration Handbook for Germany - 260807-1.pdf"
    )

    for chunk in chunks:
        print(f"\n--- CHUNK: {chunk.kind} ---\n")
        print(chunk.text)


if __name__ == "__main__":
    main()
