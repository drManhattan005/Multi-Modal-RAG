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

def find_heading_index(lines: list[str], heading: str) -> int:
    target = " ".join(heading.split()).strip().lower()

    for i, line in enumerate(lines):
        candidate = " ".join(line.split()).strip().lower()
        if candidate == target:
            return i

    for i, line in enumerate(lines):
        candidate = " ".join(line.split()).strip().lower()
        if target in candidate:
            return i

    raise ValueError(f"Heading not found: {heading}")



def build_chunks(pdf_path: str) -> list[Chunk]:
    reader = PdfReader(pdf_path)

    raw_text = ""
    for page_num in [1, 2]:
        raw_text += (reader.pages[page_num].extract_text() or "") + "\n"

    normalized = normalize_text(raw_text)
    all_lines = normalized.splitlines()
    lines = remove_footer(all_lines)

    handbook_idx = find_heading_index(lines, "WHAT YOU WILL FIND IN THIS HANDBOOK")
    promise_idx = find_heading_index(lines, "OUR PROMISE")

    intro_lines = lines[:handbook_idx]
    handbook_lines = lines[handbook_idx:promise_idx]
    promise_lines = lines[promise_idx:]

    return [
        Chunk(kind="title_intro", text="\n".join(intro_lines)),
        Chunk(kind="what_you_will_find", text="\n".join(handbook_lines)),
        Chunk(kind="our_promise", text="\n".join(promise_lines)),
    ]


def main() -> None:
    chunks = build_chunks("/Users/hrugvedambre/Documents/Veloit-Voice-Rag/Visa & Immigration Handbook for Germany - 260807-1.pdf")

    for chunk in chunks:
        print(f"\n--- CHUNK: {chunk.kind} ---\n")
        print(chunk.text)


if __name__ == "__main__":
    main()
