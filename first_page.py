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


def split_title_and_contents(lines: list[str], title_line_count: int = 1) -> tuple[list[str], list[str]]:
    if len(lines) < title_line_count:
        raise ValueError(
            f"Expected at least {title_line_count} lines for the title, found {len(lines)}"
        )
    title_lines = lines[:title_line_count]
    contents_lines = lines[title_line_count:]
    return title_lines, contents_lines


def build_chunks(pdf_path: str) -> list[Chunk]:
    reader = PdfReader(pdf_path)
    page = reader.pages[0]

    raw_text = page.extract_text() or ""
    normalized = normalize_text(raw_text)

    all_lines = [line for line in normalized.splitlines() if line.strip()]
    body_lines = all_lines[1:]

    title_lines, contents_lines = split_title_and_contents(body_lines, title_line_count=5)

    title_chunk = Chunk(kind="title", text="\n".join(title_lines))
    contents_chunk = Chunk(kind="contents", text="\n".join(contents_lines))

    return [title_chunk, contents_chunk]


def main() -> None:
    chunks = build_chunks("/Users/hrugvedambre/Documents/Veloit-Voice-Rag/Visa & Immigration Handbook for Germany - 260807-1.pdf")

    for chunk in chunks:
        print(f"\n--- CHUNK: {chunk.kind} ---\n")
        print(chunk.text)


if __name__ == "__main__":
    main()
