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
    for page_num in [22, 23, 24, 25, 26]:
        raw_text += (reader.pages[page_num].extract_text() or "") + "\n"

    normalized = normalize_text(raw_text)
    all_lines = normalized.splitlines()
    lines = remove_footer(all_lines)

    markers = [
        ("code95_intro", "EU CODE 95 & DRIVER CARD"),
        ("what_is_code95", "What Is the EU Code 95 Qualification?"),
        ("international_drivers_code95", "Can International Drivers Obtain Code 95?"),
        ("do_not_be_afraid", "Do Not Be Afraid"),
        ("what_is_driver_card", "What Is the Driver Card?"),
        ("why_driver_card_important", "Why Is the Driver Card Important?"),
        ("support_during_process", "Support During the Process"),
        ("building_qualifications", "Building Your Professional Qualifications"),
        ("remember_summary", "Remember"),
        ("our_message", "OUR MESSAGE"),
        ("recommended_training_partner", "Recommended Training Partner for Code 95"),
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
