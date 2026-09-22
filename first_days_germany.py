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


def find_exact_heading_index(lines: list[str], heading: str, start: int = 0) -> int:
    """Requires an exact line match, so body text mentioning the heading word is ignored."""
    target = normalize_for_match(heading)

    for i in range(start, len(lines)):
        candidate = normalize_for_match(lines[i])

        if candidate == target:
            return i

    raise ValueError(f"Heading not found (exact match required): {heading}")


def build_chunks(pdf_path: str) -> list[Chunk]:
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
