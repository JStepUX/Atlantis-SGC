"""Categorical index construction (companion artifact, not chunk frontmatter).

Follows the schema's Construction Logic:

1. Identify root terms per source document: content terms that repeat at least
   ``root_min_count`` times, ranked by count x idf (favours distinctive repeats).
2. A document with >= ``root_min_distinct`` distinct roots earns an index entry,
   keyed by its document_slug.
3. Sibling detection runs TF-IDF cosine similarity between entry vectors (the
   mean of each entry's chunk vectors); pairs above ``sibling_threshold`` are
   siblings, recorded with their score.
4. Emit index.json (machine) and index.md (human). Each chunk's index_ref is set
   to {entry, line}, where line is the entry's line in index.md.

NOTE: this implements the literal per-document construction logic. Cross-document
categorical merging (the schema's "brazilian-jiu-jitsu" example grouping two
different source files) is an open question and intentionally left for later.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import numpy as np

from .config import Config
from .models import Chunk
from .salience import TfidfModel
from .textutils import content_terms


def _document_roots(
    chunk_terms: list[list[str]], tfidf: TfidfModel, cfg: Config
) -> list[str]:
    """Root terms for one document, ranked by repetition x distinctiveness."""
    counts: Counter[str] = Counter()
    for terms in chunk_terms:
        counts.update(terms)
    scored: list[tuple[float, str]] = []
    for term, c in counts.items():
        if c < cfg.index.root_min_count:
            continue
        j = tfidf.vocab.get(term)
        idf = tfidf.idf[j] if j is not None else 1.0
        scored.append((c * idf, term))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [term for _, term in scored[: cfg.index.root_top_k]]


def _entry_vector(chunk_ids: list[str], tfidf: TfidfModel) -> np.ndarray:
    rows = [
        tfidf.matrix[tfidf.chunk_ids.index(cid)]
        for cid in chunk_ids
        if cid in tfidf.chunk_ids
    ]
    if not rows:
        return np.zeros(len(tfidf.vocab))
    vec = np.mean(rows, axis=0)
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


def build_index(
    chunks: list[Chunk], tfidf: TfidfModel, cfg: Config, generated_at: str
) -> dict[str, Any]:
    """Build entries + siblings, assign index_ref to chunks, return index data."""
    by_doc: dict[str, list[Chunk]] = defaultdict(list)
    for c in chunks:
        by_doc[c.document_slug].append(c)

    entries: dict[str, dict[str, Any]] = {}
    entry_vectors: dict[str, np.ndarray] = {}

    for slug in sorted(by_doc):
        doc_chunks = sorted(by_doc[slug], key=lambda c: c.index)
        chunk_terms = [tfidf.term_lists.get(c.chunk_id, content_terms(c.body)) for c in doc_chunks]
        roots = _document_roots(chunk_terms, tfidf, cfg)
        if len(roots) < cfg.index.root_min_distinct:
            continue  # below threshold -> no entry, chunks keep index_ref = null
        child_ids = [c.chunk_id for c in doc_chunks]
        entries[slug] = {"root_terms": roots, "children": child_ids, "siblings": {}}
        entry_vectors[slug] = _entry_vector(child_ids, tfidf)

    # Sibling similarity (symmetric).
    keys = list(entries.keys())
    for i in range(len(keys)):
        for k in range(i + 1, len(keys)):
            a, b = keys[i], keys[k]
            sim = float(np.dot(entry_vectors[a], entry_vectors[b]))
            if sim >= cfg.index.sibling_threshold:
                score = round(sim, 3)
                entries[a]["siblings"][b] = score
                entries[b]["siblings"][a] = score

    index_data = {
        "generated_at": generated_at,
        "corpus_stats": {
            "total_documents": len(by_doc),
            "total_chunks": len(chunks),
            "total_entries": len(entries),
        },
        "entries": entries,
    }

    # Render index.md, capturing each entry's line number, then back-fill chunks.
    md_text, entry_lines = render_index_md(index_data)
    index_data["_md_text"] = md_text  # consumed by pipeline writer, stripped before json

    entry_of_chunk = {
        cid: slug for slug, e in entries.items() for cid in e["children"]
    }
    for c in chunks:
        slug = entry_of_chunk.get(c.chunk_id)
        if slug is not None:
            c.index_entry = slug
            c.index_line = entry_lines.get(slug)
        else:
            c.index_entry = None
            c.index_line = None

    return index_data


def render_index_md(index_data: dict[str, Any]) -> tuple[str, dict[str, int]]:
    """Render a human-readable index.md, returning (text, {entry: line_number})."""
    lines: list[str] = []
    entry_lines: dict[str, int] = {}

    def emit(s: str = "") -> None:
        lines.append(s)

    stats = index_data["corpus_stats"]
    emit("# Atlantis Categorical Index")
    emit()
    emit(f"_Generated: {index_data['generated_at']}_")
    emit()
    emit(
        f"- Documents: {stats['total_documents']}  "
        f"- Chunks: {stats['total_chunks']}  "
        f"- Entries: {stats['total_entries']}"
    )
    emit()

    for slug in sorted(index_data["entries"]):
        entry = index_data["entries"][slug]
        entry_lines[slug] = len(lines) + 1  # 1-based line number of the header
        emit(f"## {slug}")
        emit()
        emit(f"- **root_terms:** {', '.join(entry['root_terms'])}")
        emit(f"- **children:** {len(entry['children'])} chunks")
        if entry["siblings"]:
            sib = ", ".join(f"{k} ({v})" for k, v in sorted(entry["siblings"].items()))
            emit(f"- **siblings:** {sib}")
        else:
            emit("- **siblings:** none")
        emit()

    return "\n".join(lines) + "\n", entry_lines
