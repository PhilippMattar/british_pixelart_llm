"""Read a txt/pdf document and split it into overlapping chunks (§10).

~500-token chunks are approximated by word count (~350 words); overlap keeps context from being
split across a boundary. pypdf handles PDFs; everything else is read as text.
"""

from __future__ import annotations

from pathlib import Path

CHUNK_WORDS = 350
OVERLAP_WORDS = 60


def read_document(path: str) -> str:
    """Extract text from a .pdf (pypdf) or read any other file as UTF-8 text."""
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        from pypdf import PdfReader  # lazy: only needed for PDFs

        reader = PdfReader(str(p))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return p.read_text(encoding="utf-8", errors="ignore")


def chunk_text(
    text: str, chunk_words: int = CHUNK_WORDS, overlap_words: int = OVERLAP_WORDS
) -> list[str]:
    """Overlapping word-window chunks. Overlap must be smaller than the window."""
    words = text.split()
    if not words:
        return []
    step = max(1, chunk_words - overlap_words)
    chunks: list[str] = []
    start = 0
    while start < len(words):
        chunks.append(" ".join(words[start : start + chunk_words]))
        if start + chunk_words >= len(words):
            break
        start += step
    return chunks
