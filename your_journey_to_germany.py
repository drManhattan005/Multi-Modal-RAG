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


def find_line_index_contains(lines: list[str], needle: str, start: int = 0) -> int:
    target = normalize_for_match(needle)

    for i in range(start, len(lines)):
        candidate = normalize_for_match(lines[i])

        if candidate == target:
            return i

    for i in range(start, len(lines)):
        candidate = normalize_for_match(lines[i])

        if target in candidate:
            return i

    raise ValueError(f"Heading not found: {needle}")


def find_optional_line_index_contains(lines: list[str], needle: str, start: int = 0) -> int | None:
    target = normalize_for_match(needle)

    for i in range(start, len(lines)):
        candidate = normalize_for_match(lines[i])

        if candidate == target or target in candidate:
            return i

    return None


def find_step_index(lines: list[str], step_number: int, start: int = 0) -> int:
    target = f"step {step_number}"

    for i in range(start, len(lines)):
        candidate = normalize_for_match(lines[i])

        if candidate == target:
            return i

    for i in range(start, len(lines)):
        candidate = normalize_for_match(lines[i])

        if candidate.startswith(target):
            return i

    raise ValueError(f"Step heading not found: STEP {step_number}")


def build_chunks(pdf_path: str) -> list[Chunk]:
    reader = PdfReader(pdf_path)

    raw_text = ""

    # PDF pages 10, 11, 12, 13 -> zero-based indices 9, 10, 11, 12
    for page_num in [9, 10, 11, 12]:
        raw_text += (reader.pages[page_num].extract_text() or "") + "\n"

    normalized = normalize_text(raw_text)
    all_lines = normalized.splitlines()
    lines = remove_footer(all_lines)

    intro_heading_idx = find_line_index_contains(lines, "YOUR JOURNEY TO GERMANY")

    step_indices = []
    search_start = 0

    for step_number in range(1, 11):
        idx = find_step_index(lines, step_number, start=search_start)
        step_indices.append((f"step_{step_number}", idx))
        search_start = idx + 1

    chunks = []

    intro_lines = lines[intro_heading_idx:step_indices[0][1]]
    chunks.append(Chunk(kind="journey_intro", text="\n".join(intro_lines)))

    for i, (kind, start_idx) in enumerate(step_indices[:-1]):
        end_idx = step_indices[i + 1][1]
        chunk_lines = lines[start_idx:end_idx]
        chunks.append(Chunk(kind=kind, text="\n".join(chunk_lines)))

    step_10_start = step_indices[-1][1]
    remember_idx = find_optional_line_index_contains(lines, "REMEMBER", start=step_10_start)

    if remember_idx is not None:
        step_10_lines = lines[step_10_start:remember_idx]
        remember_lines = lines[remember_idx:]

        chunks.append(Chunk(kind="step_10", text="\n".join(step_10_lines)))
        chunks.append(Chunk(kind="remember_summary", text="\n".join(remember_lines)))
    else:
        step_10_lines = lines[step_10_start:]
        chunks.append(Chunk(kind="step_10", text="\n".join(step_10_lines)))

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
