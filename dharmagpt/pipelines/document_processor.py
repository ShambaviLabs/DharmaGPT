"""Convert text documents (PDF, TXT, MD) into DharmaGPT JSONL records."""
from __future__ import annotations

import re
import uuid
from pathlib import Path

SUPPORTED_DOC_FORMATS = {".pdf", ".txt", ".md", ".text"}


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError("pypdf not installed — run: pip install pypdf")
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix in {".txt", ".md", ".text"}:
        return _extract_text(path)
    raise ValueError(f"Unsupported document format: {suffix}")


def _chunk(text: str, chunk_words: int = 400, overlap: int = 40) -> list[str]:
    words = text.split()
    out, i = [], 0
    while i < len(words):
        out.append(" ".join(words[i : i + chunk_words]))
        i += chunk_words - overlap
    return [c for c in out if len(c.split()) >= 20]


def process_document(
    path: Path,
    *,
    source: str | None = None,
    language: str = "en",
    source_type: str = "text",
    description: str | None = None,
    section: str = "",
) -> list[dict]:
    raw = extract_text(path)
    raw = re.sub(r"\s+", " ", raw).strip()
    if not raw:
        return []

    source = source or re.sub(r"[^a-z0-9]+", "_", path.stem.lower()).strip("_")
    chunks = _chunk(raw)
    records = []
    for i, chunk in enumerate(chunks):
        records.append({
            "id": f"{source}_{uuid.uuid4().hex[:8]}_{i:04d}",
            "text": chunk,
            "source": source,
            "section": section,
            "citation": description or path.name,
            "language": language,
            "source_type": source_type,
            "tags": ["story"],
            "topics": [],
            "characters": [],
            "is_shloka": False,
            "url": "",
            "notes": f"Extracted from {path.name}",
            "source_file": path.name,
        })
    return records
