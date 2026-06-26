"""Document discovery and chunking.

Strategy (markdown-aware, token-bounded):

1. Split the document into blocks at markdown headings (``#``..``######``).
   Each heading opens a new section so chunks don't straddle topic boundaries.
2. Within a section, pack paragraphs (blank-line separated) until ``target_tokens``.
3. A single paragraph larger than ``max_tokens`` is split on sentence boundaries.
4. Trailing chunks below ``min_tokens`` are merged backward when that keeps the
   merged chunk under ``max_tokens``.

Plain-text files (no headings) fall through the same packer with one big section.
"""

from __future__ import annotations

import re
from pathlib import Path

from .config import ROOT, ChunkingConfig
from .models import Chunk, Document
from .textutils import estimate_tokens, slugify

RAW_EXTENSIONS = {".md", ".markdown", ".txt", ".text"}
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def discover_documents(raw_dir: Path) -> list[Document]:
    """Find raw documents under ``raw_dir`` (recursive), sorted for determinism."""
    docs: list[Document] = []
    if not raw_dir.exists():
        return docs
    for path in sorted(raw_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in RAW_EXTENSIONS:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        slug = slugify(path.stem)
        try:
            rel = path.relative_to(ROOT).as_posix()
        except ValueError:
            rel = path.as_posix()
        docs.append(
            Document(
                slug=slug,
                source_file=rel,
                title=_extract_title(text, path.stem),
                text=text,
            )
        )
    return docs


def _extract_title(text: str, fallback_stem: str) -> str:
    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            return m.group(2).strip()
    # De-slug the filename: "kimura-grip-mechanics" -> "Kimura Grip Mechanics"
    return re.sub(r"[-_]+", " ", fallback_stem).strip().title()


def _split_into_sections(text: str) -> list[tuple[str, str]]:
    """Return [(heading, body_text)]. Heading is "" for pre-heading content."""
    sections: list[tuple[str, list[str]]] = []
    current_heading = ""
    current_lines: list[str] = []

    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            if current_lines:
                sections.append((current_heading, current_lines))
            current_heading = m.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_heading, current_lines))

    return [(h, "\n".join(lines).strip()) for h, lines in sections if "".join(lines).strip()]


def _paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n\s*\n", text)
    return [p.strip() for p in parts if p.strip()]


def _split_oversized(paragraph: str, max_tokens: int) -> list[str]:
    """Split a too-large paragraph on sentence boundaries, packing to max_tokens."""
    sentences = _SENTENCE_RE.split(paragraph)
    out: list[str] = []
    buf: list[str] = []
    buf_tok = 0
    for s in sentences:
        st = estimate_tokens(s)
        if buf and buf_tok + st > max_tokens:
            out.append(" ".join(buf))
            buf, buf_tok = [], 0
        buf.append(s)
        buf_tok += st
    if buf:
        out.append(" ".join(buf))
    return out


def _pack(sections: list[tuple[str, str]], cfg: ChunkingConfig) -> list[tuple[str, str]]:
    """Pack section paragraphs into (heading, body) chunk tuples."""
    raw_chunks: list[tuple[str, str]] = []

    for heading, body in sections:
        paras = _paragraphs(body) if body else []
        buf: list[str] = []
        buf_tok = 0

        def flush() -> None:
            nonlocal buf, buf_tok
            if buf:
                raw_chunks.append((heading, "\n\n".join(buf)))
                buf, buf_tok = [], 0

        for para in paras:
            ptok = estimate_tokens(para)
            if ptok > cfg.max_tokens:
                flush()
                for piece in _split_oversized(para, cfg.max_tokens):
                    raw_chunks.append((heading, piece))
                continue
            if buf and buf_tok + ptok > cfg.target_tokens:
                flush()
            buf.append(para)
            buf_tok += ptok
        flush()

    return _merge_small(raw_chunks, cfg)


def _merge_small(chunks: list[tuple[str, str]], cfg: ChunkingConfig) -> list[tuple[str, str]]:
    """Merge sub-min chunks backward into the previous chunk when it fits."""
    merged: list[tuple[str, str]] = []
    for heading, body in chunks:
        tok = estimate_tokens(body)
        if (
            merged
            and tok < cfg.min_tokens
            and estimate_tokens(merged[-1][1]) + tok <= cfg.max_tokens
        ):
            prev_h, prev_b = merged[-1]
            merged[-1] = (prev_h, f"{prev_b}\n\n{body}")
        else:
            merged.append((heading, body))
    return merged


def chunk_document(doc: Document, cfg: ChunkingConfig) -> list[Chunk]:
    """Split one document into ordered, identity-stamped Chunk objects."""
    if cfg.respect_headings:
        sections = _split_into_sections(doc.text)
    else:
        sections = [("", doc.text.strip())]
    if not sections:
        sections = [("", doc.text.strip())]

    packed = _pack(sections, cfg)
    if not packed:  # empty / whitespace-only document
        return []

    total = len(packed)
    chunks: list[Chunk] = []
    for i, (heading, body) in enumerate(packed):
        chunk_id = f"{doc.slug}_{i:03d}"
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                document_slug=doc.slug,
                source_file=doc.source_file,
                document_title=doc.title,
                index=i,
                total=total,
                heading=heading,
                body=body,
                tokens=estimate_tokens(body),
            )
        )

    # Link navigation now that the full sequence is known.
    for i, c in enumerate(chunks):
        c.previous_id = chunks[i - 1].chunk_id if i > 0 else None
        c.next_id = chunks[i + 1].chunk_id if i < total - 1 else None

    return chunks
