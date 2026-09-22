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
    chunks.append(Chunk(kind="page_title_intro", text="\n".join(intro_lines)))

    for i, (kind, heading, start_idx) in enumerate(indices):
        end_idx = indices[i + 1][2] if i + 1 < len(indices) else len(lines)
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
