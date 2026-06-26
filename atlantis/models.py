"""Shared data models that flow through the pipeline.

A ``Chunk`` starts life with just identity + body (from chunking) and is
progressively enriched: salience scores, classification, navigation, index
reference, then a fully assembled frontmatter dict ready for emit + Chroma.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Document:
    """A raw source document discovered under the raw dir."""

    slug: str               # filename stem, slugified -> document_slug
    source_file: str        # path relative to project root, for provenance
    title: str              # human title (first heading or de-slugged name)
    text: str               # full raw text


@dataclass
class Chunk:
    """One chunk and everything computed about it during ingest."""

    # --- identity (chunking) ---
    chunk_id: str
    document_slug: str
    source_file: str
    document_title: str
    index: int              # 0-based position within the document
    total: int              # total chunks in the document
    heading: str            # nearest markdown heading, "" if none
    body: str               # chunk text (below the frontmatter)
    tokens: int = 0

    # --- salience (TF-IDF pass) ---
    lexical_distinctiveness: float = 0.0
    information_density: float = 0.0

    # --- classification (small model) ---
    chunk_type: str = "section"
    summary: str = ""
    topics: list[dict[str, Any]] = field(default_factory=list)   # [{topic, depth}]
    aliases: dict[str, str] = field(default_factory=dict)
    goal_affinity: list[dict[str, Any]] = field(default_factory=list)  # [{domain, weight}]
    utility: str = "declarative"
    authority: str = "canonical"
    confidence: float = 0.8
    standalone: bool = True
    specificity: float = 0.0

    # --- navigation / relations ---
    next_id: str | None = None
    previous_id: str | None = None
    related_chunks: list[str] = field(default_factory=list)

    # --- index reference (post-index build) ---
    index_entry: str | None = None
    index_line: int | None = None

    # --- assembled output ---
    frontmatter: dict[str, Any] = field(default_factory=dict)

    @property
    def content_term_cache_key(self) -> str:
        return self.chunk_id
