"""Chroma persistence.

Chroma metadata only supports str/int/float/bool (no None, no nested objects),
so frontmatter is flattened per the schema's "Chroma Metadata Mapping":

* scalars are copied with the schema's Chroma key names,
* nulls become "" (empty string),
* topics / goal_affinity / aliases are stored as JSON strings (``*_json``),
* a few extra retrieval-convenience keys (document_title, index_entry, nav_*)
  are added so the orchestrator can fan out from a pure-Chroma hit.

The stored *document* text is the body augmented with aliases (per
embeddings.alias_strategy) so alias terms participate in the embedding geometry.
"""

from __future__ import annotations

import json
from typing import Any

import chromadb
from chromadb.utils import embedding_functions

from .config import Config
from .models import Chunk


def build_embedding_text(chunk: Chunk, cfg: Config) -> str:
    """Body + alias expansion, controlled by embeddings.alias_strategy."""
    strategy = cfg.embeddings.alias_strategy
    if not chunk.aliases or strategy == "none":
        return chunk.body.strip()
    alias_line = "Also known as: " + "; ".join(
        f"{k} = {v}" for k, v in chunk.aliases.items()
    )
    if strategy == "prepend":
        return f"{alias_line}\n\n{chunk.body.strip()}"
    return f"{chunk.body.strip()}\n\n{alias_line}"  # append (default)


def _s(val: Any) -> str:
    """None/blank -> '', else str."""
    return "" if val is None else str(val)


def flatten_metadata(fm: dict[str, Any]) -> dict[str, Any]:
    """Frontmatter dict -> flat Chroma metadata (no None, no nesting)."""
    prov = fm.get("provenance", {})
    sal = fm.get("salience", {})
    temporal = fm.get("temporal", {})
    nav = fm.get("navigation", {})
    index_ref = fm.get("index_ref") or {}

    meta: dict[str, Any] = {
        # --- schema mapping table ---
        "chunk_id": fm["chunk_id"],
        "document_slug": fm["document_slug"],
        "chunk_type": fm["chunk_type"],
        "topic_path": fm["topic_path"],
        "utility": fm["utility"],
        "provenance_source_type": prov.get("source_type", ""),
        "provenance_authority": prov.get("authority", ""),
        "provenance_confidence": float(prov.get("confidence", 0.0)),
        "status": fm.get("status", "active"),
        "temporal_decay_class": temporal.get("decay_class", ""),
        "temporal_created_at": _s(temporal.get("created_at")),
        "temporal_stale_after": _s(temporal.get("stale_after")),
        "salience_standalone": bool(sal.get("standalone", True)),
        "salience_lexical_dist": float(sal.get("lexical_distinctiveness", 0.0)),
        "salience_info_density": float(sal.get("information_density", 0.0)),
        "salience_specificity": float(sal.get("specificity", 0.0)),
        "tokens": int(fm.get("tokens", 0)),
        # JSON-encoded structures
        "topics_json": json.dumps(fm.get("topics", []), ensure_ascii=False),
        "goal_affinity_json": json.dumps(fm.get("goal_affinity", []), ensure_ascii=False),
        "aliases_json": json.dumps(fm.get("aliases", {}), ensure_ascii=False),
        # --- retrieval-convenience extras (enable fan-out from a Chroma hit) ---
        "document_title": _s(fm.get("document_title")),
        "index_entry": _s(index_ref.get("entry")),
        "nav_current": int(nav.get("current", 0)),
        "nav_total": int(nav.get("total", 0)),
        "nav_next": _s(nav.get("next")),
        "nav_previous": _s(nav.get("previous")),
    }
    return meta


class ChromaWriter:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        cfg.paths.chroma_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(cfg.paths.chroma_dir))
        self.embedding_fn = embedding_functions.DefaultEmbeddingFunction()
        self.collection = self.client.get_or_create_collection(
            name=cfg.embeddings.collection_name,
            # chromadb's own DefaultEmbeddingFunction doesn't satisfy its
            # EmbeddingFunction protocol under strict typing — library friction.
            embedding_function=self.embedding_fn,  # type: ignore[arg-type]
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_chunks(self, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        ids = [c.chunk_id for c in chunks]
        documents = [build_embedding_text(c, self.cfg) for c in chunks]
        metadatas = [flatten_metadata(c.frontmatter) for c in chunks]
        # Upsert in batches to keep memory + embed calls bounded.
        batch = 128
        for i in range(0, len(ids), batch):
            self.collection.upsert(
                ids=ids[i : i + batch],
                documents=documents[i : i + batch],
                # list[dict[str, Any]] vs chromadb's Mapping union (list is
                # invariant); our values are all str|int|float|bool in practice.
                metadatas=metadatas[i : i + batch],  # type: ignore[arg-type]
            )
        return len(ids)

    def count(self) -> int:
        return self.collection.count()

    def query(self, text: str, n: int = 5, where: dict | None = None):
        return self.collection.query(query_texts=[text], n_results=n, where=where)
