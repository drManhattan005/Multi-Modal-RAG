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


def find_heading_index(
    lines: list[str],
    heading: str,
    start: int = 0,
) -> int | None:
    target = normalize_for_match(heading)

    # Exact normalized line match.
    for i in range(start, len(lines)):
        candidate = normalize_for_match(lines[i])

        if candidate == target:
            return i

    # Heading may be merged with extracted text.
    for i in range(start, len(lines)):
        candidate = normalize_for_match(lines[i])

        if target in candidate:
            return i

    # Heading may be split across two extracted lines.
    for i in range(start, len(lines) - 1):
        combined = normalize_for_match(lines[i] + " " + lines[i + 1])

        if combined == target or target in combined:
            return i

    return None


def build_chunks(pdf_path: str) -> list[Chunk]:
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
        markers.append(
            (
                f"faq_{question_number}",
                f"{question_number}.",
            )
        )

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
        chunks.append(Chunk(kind=kind, text=chunk_text))

    return chunks


def find_question_index(
    lines: list[str],
    question_number: int,
    start: int = 0,
) -> int | None:
    """
    Find a numbered FAQ question without confusing it with page numbers
    or numbered content elsewhere.
    """
    prefix = f"{question_number}."

    for i in range(start, len(lines)):
        candidate = normalize_for_match(lines[i])

        if not candidate.startswith(prefix):
            continue

        remainder = candidate[len(prefix):].strip()

        # A valid FAQ question should contain words after "N."
        if remainder:
            return i

    return None


def main() -> None:
    chunks = build_chunks(
        "/Users/hrugvedambre/Documents/Veloit-Voice-Rag/Visa & Immigration Handbook for Germany - 260807-1.pdf"
    )

    for chunk in chunks:
        print(f"\n--- CHUNK: {chunk.kind} ---\n")
        print(chunk.text)


if __name__ == "__main__":
    main()
