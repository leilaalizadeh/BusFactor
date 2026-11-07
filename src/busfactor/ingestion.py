"""Ingestion — read project files as numbered pages of plain text (Teammate 1).

Only text is extracted. Uploaded content is never executed, imported or evaluated.

Page numbering (this is what DecisionCard.source_refs[].page refers to):
- PDF:      the real PDF page number (1-based), via pdfplumber.
- .md/.txt: pages are separated by lines containing only `---`, numbered from 1.
            A file with no `---` lines is cut into ~3000-character chunks instead.
Empty pages are left out but keep their number, so citations never shift.
"""
from __future__ import annotations

import re
from pathlib import Path

CHUNK_CHARS = 3000
TEXT_SUFFIXES = {".md", ".markdown", ".txt"}
_PAGE_BREAK = re.compile(r"^[ \t]*---[ \t]*$", flags=re.MULTILINE)


def load_pages(path: str | Path) -> list[tuple[int, str]]:
    """Return [(page_number, text), ...] for a PDF, Markdown or text file.

    An empty file gives []. A missing file raises FileNotFoundError;
    an unsupported file type raises ValueError.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"No such file: {path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _load_pdf(path)
    if suffix in TEXT_SUFFIXES:
        return _load_text(path.read_text(encoding="utf-8", errors="replace"))
    raise ValueError(f"Unsupported file type '{suffix}'. Use .pdf, .md or .txt.")


def _load_pdf(path: Path) -> list[tuple[int, str]]:
    # Imported here so Markdown/text ingestion works even without pdfplumber installed.
    import pdfplumber

    pages: list[tuple[int, str]] = []
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:  # scanned/blank pages have no text layer -> skipped, number kept
                pages.append((number, text))
    return pages


def _load_text(text: str) -> list[tuple[int, str]]:
    if _PAGE_BREAK.search(text):
        parts = _PAGE_BREAK.split(text)
    else:
        parts = _chunk(text, CHUNK_CHARS)
    return [(number, part.strip()) for number, part in enumerate(parts, start=1) if part.strip()]


def _chunk(text: str, size: int) -> list[str]:
    """Split text into pieces of at most ~size characters, preferring paragraph or line breaks."""
    chunks: list[str] = []
    while len(text) > size:
        cut = max(text.rfind("\n\n", 0, size), text.rfind("\n", 0, size))
        if cut <= 0:
            cut = text.rfind(" ", 0, size)
        if cut <= 0:  # one very long word: hard cut
            cut = size
        chunks.append(text[:cut])
        text = text[cut:]
    chunks.append(text)
    return chunks
