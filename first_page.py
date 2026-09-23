import json
from pathlib import Path

from pypdf import PdfReader


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00ad", "")
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(lines).strip()


def split_title_and_contents(
    lines: list[str],
    title_line_count: int = 1,
) -> tuple[list[str], list[str]]:
    if len(lines) < title_line_count:
        raise ValueError(
            f"Expected at least {title_line_count} lines for the title, found {len(lines)}"
        )

    title_lines = lines[:title_line_count]
    contents_lines = lines[title_line_count:]
    return title_lines, contents_lines


CHUNK_METADATA = {
    "title": {
        "chunk_id": "first_page_title",
        "chunk_kind": "intro",
        "section_title": "Cover Page",
        "subsection_title": "Title",
        "topic_tags": [
            "cover_page",
            "title",
            "handbook",
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
    "contents": {
        "chunk_id": "first_page_contents",
        "chunk_kind": "summary",
        "section_title": "Cover Page",
        "subsection_title": "Contents Overview",
        "topic_tags": [
            "contents",
            "handbook_overview",
            "sections",
            "navigation",
            "table_of_contents",
        ],
        "intent_type": "explanation",
        "entity_tags": [
            "EuroJobsCenter",
            "Germany",
            "Code 95",
            "Driver Card",
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
    page = reader.pages[0]

    raw_text = page.extract_text() or ""
    normalized = normalize_text(raw_text)

    all_lines = [line for line in normalized.splitlines() if line.strip()]
    body_lines = all_lines[1:]

    title_lines, contents_lines = split_title_and_contents(
        body_lines,
        title_line_count=5,
    )

    return [
        make_chunk("title", "\n".join(title_lines)),
        make_chunk("contents", "\n".join(contents_lines)),
    ]


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
        "output/first_page.jsonl"
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
