"""Frontmatter assembly, validation, and emit.

Takes a fully-enriched Chunk (chunking + salience + classification + navigation
+ index_ref) and produces the ordered YAML frontmatter dict defined by the
Atlantis Salience Schema v1.0, plus helpers to validate it and write the chunk
file (frontmatter + body) to disk.

Derived fields computed here:
* topic_path  — topics sorted by depth ascending, names joined with "."
* specificity — depth-0 topic count / total topics (concrete vs. abstract)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .classify import AUTHORITIES, CHUNK_TYPES, UTILITIES
from .config import Config
from .models import Chunk

DECAY_CLASSES = {"evergreen", "slow-decay", "fast-decay", "ephemeral"}
SOURCE_TYPES = {"human-authored", "model-generated", "system-event", "conversation"}
STATUSES = {"active", "draft", "superseded", "archived"}


def derive_topic_path(topics: list[dict[str, Any]]) -> str:
    """Sort by depth ascending (stable), join topic names with dots."""
    ordered = sorted(topics, key=lambda t: t.get("depth", 0))
    return ".".join(t["topic"] for t in ordered if t.get("topic"))


def derive_specificity(topics: list[dict[str, Any]]) -> float:
    if not topics:
        return 0.0
    depth0 = sum(1 for t in topics if t.get("depth", 0) == 0)
    return round(depth0 / len(topics), 3)


def _none_if_blank(val: str) -> str | None:
    return val if val else None


def assemble_frontmatter(chunk: Chunk, cfg: Config, created_at: str) -> dict[str, Any]:
    """Build the ordered frontmatter dict for a chunk."""
    topic_path = derive_topic_path(chunk.topics)
    specificity = derive_specificity(chunk.topics)
    chunk.specificity = specificity  # keep the Chunk in sync for downstream use

    fm: dict[str, Any] = {
        # IDENTITY
        "chunk_id": chunk.chunk_id,
        "document_slug": chunk.document_slug,
        "source_file": chunk.source_file,
        # CONTENT DESCRIPTION
        "chunk_type": chunk.chunk_type,
        "document_title": chunk.document_title,
        "summary": chunk.summary,
        "topics": [{"topic": t["topic"], "depth": t["depth"]} for t in chunk.topics],
        "topic_path": topic_path,
        "aliases": dict(chunk.aliases),
        # NAVIGATION
        "navigation": {
            "current": chunk.index,
            "total": chunk.total,
            "next": chunk.next_id,
            "previous": chunk.previous_id,
        },
        "series": None,
        "related_chunks": list(chunk.related_chunks),
        # INDEX REFERENCE
        "index_ref": (
            {"entry": chunk.index_entry, "line": chunk.index_line}
            if chunk.index_entry is not None
            else None
        ),
        # SALIENCE
        "salience": {
            "lexical_distinctiveness": chunk.lexical_distinctiveness,
            "information_density": chunk.information_density,
            "specificity": specificity,
            "standalone": chunk.standalone,
        },
        # GOAL BINDING
        "goal_affinity": [
            {"domain": g["domain"], "weight": g["weight"]} for g in chunk.goal_affinity
        ],
        "utility": chunk.utility,
        # PROVENANCE
        "provenance": {
            "source_type": cfg.provenance.source_type,
            "authority": chunk.authority,
            "confidence": chunk.confidence,
            "author": _none_if_blank(cfg.provenance.author),
            "original_source": _none_if_blank(cfg.provenance.original_source),
        },
        # LIFECYCLE
        "status": "active",
        # TEMPORAL
        "temporal": {
            "created_at": created_at,
            "effective_date": None,
            "stale_after": None,
            "decay_class": cfg.temporal.decay_class,
            "last_accessed": None,
            "access_count": 0,
        },
        # CONTENT
        "tokens": chunk.tokens,
    }
    return fm


def validate_frontmatter(fm: dict[str, Any]) -> list[str]:
    """Return a list of human-readable problems (empty = valid)."""
    problems: list[str] = []

    def need(cond: bool, msg: str) -> None:
        if not cond:
            problems.append(msg)

    cid = fm.get("chunk_id", "?")
    need(bool(fm.get("chunk_id")), "missing chunk_id")
    need(bool(fm.get("document_slug")), f"{cid}: missing document_slug")
    need(fm.get("chunk_type") in CHUNK_TYPES, f"{cid}: bad chunk_type {fm.get('chunk_type')!r}")
    need(fm.get("utility") in UTILITIES, f"{cid}: bad utility {fm.get('utility')!r}")
    need(bool(fm.get("summary")), f"{cid}: empty summary")
    need(bool(fm.get("topics")), f"{cid}: no topics")
    need(bool(fm.get("topic_path")), f"{cid}: empty topic_path")

    prov = fm.get("provenance", {})
    need(prov.get("source_type") in SOURCE_TYPES, f"{cid}: bad source_type")
    need(prov.get("authority") in AUTHORITIES, f"{cid}: bad authority")
    need(0.0 <= prov.get("confidence", -1) <= 1.0, f"{cid}: confidence out of range")

    sal = fm.get("salience", {})
    for k in ("lexical_distinctiveness", "information_density", "specificity"):
        v = sal.get(k, -1)
        need(0.0 <= v <= 1.0, f"{cid}: salience.{k} out of range ({v})")
    need(isinstance(sal.get("standalone"), bool), f"{cid}: standalone not bool")

    temporal = fm.get("temporal", {})
    need(temporal.get("decay_class") in DECAY_CLASSES, f"{cid}: bad decay_class")
    need(fm.get("status") in STATUSES, f"{cid}: bad status")
    need(isinstance(fm.get("tokens"), int) and fm["tokens"] >= 0, f"{cid}: bad tokens")

    return problems


def to_yaml(fm: dict[str, Any]) -> str:
    """Serialize frontmatter preserving the schema's field order."""
    return yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, width=100)


def write_chunk_file(chunk: Chunk, chunks_dir: Path) -> Path:
    """Write '<chunk_id>.md' = frontmatter + body. Returns the path."""
    chunks_dir.mkdir(parents=True, exist_ok=True)
    out_path = chunks_dir / f"{chunk.chunk_id}.md"
    doc = f"---\n{to_yaml(chunk.frontmatter)}---\n\n{chunk.body.strip()}\n"
    out_path.write_text(doc, encoding="utf-8")
    return out_path
