"""End-to-end ingest orchestration.

Atlantis exists to compile brain packs for the sibling SGC repo, so the
DEFAULT run is the lean compile path — only the stages whose output the
`export` command actually reads:

  discover -> chunk -> classify -> assemble+validate frontmatter
  -> write chunk files -> stamp backend into index.json -> report

`full=True` (CLI: `ingest --full`) restores the original vector-pipeline
tail — TF-IDF salience, related_chunks, the categorical index, and the
Chroma/MiniLM upsert. That tail is retained as dormant infrastructure for
the Phase 2b embeddings-vs-lexical comparison and a future sgc-brain/2
(salience-weighted retrieval); it is NOT part of the current pack contract.
Tail ordering when it runs: salience needs the whole corpus (TF-IDF), the
index needs salience's TF-IDF model, and related_chunks needs the model's
topics.

Either mode writes index.json with the `backend` stamp — the one key the
exporter reads (source.stub provenance). Do not decouple that stamp from
the file write; a missing/unstamped index.json silently degrades every
pack to stub=false.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .chunking import chunk_document, discover_documents
from .classify import make_classifier
from .config import Config
from .models import Chunk
from .reporting import Reporter, ConsoleReporter
from .schema import assemble_frontmatter, validate_frontmatter, write_chunk_file

# The Phase 2b tail (salience/index/chroma) imports lazily inside its `full`
# branches — salience and index_builder pull in numpy, chroma_writer pulls in
# chromadb + the MiniLM ONNX stack. A compile-only environment needs none of
# them installed.


@dataclass
class IngestReport:
    documents: int = 0
    chunks: int = 0
    entries: int = 0
    classified_ok: int = 0
    classify_fallbacks: int = 0
    validation_problems: list[str] = field(default_factory=list)
    chroma_count: int = 0
    backend: str = ""


def _topic_set(chunk: Chunk) -> set[str]:
    return {t["topic"] for t in chunk.topics}


def _compute_related(chunks: list[Chunk], cfg: Config) -> None:
    """related_chunks: cross-document topic-set overlap (Jaccard), top-N per chunk."""
    topic_sets = {c.chunk_id: _topic_set(c) for c in chunks}
    for c in chunks:
        ts = topic_sets[c.chunk_id]
        if not ts:
            continue
        scored: list[tuple[float, str]] = []
        for other in chunks:
            if other.document_slug == c.document_slug:
                continue
            os = topic_sets[other.chunk_id]
            if not os:
                continue
            inter = len(ts & os)
            if inter == 0:
                continue
            union = len(ts | os)
            jac = inter / union
            if jac >= cfg.salience.related_min_overlap:
                scored.append((jac, other.chunk_id))
        scored.sort(key=lambda x: (-x[0], x[1]))
        c.related_chunks = [cid for _, cid in scored[: cfg.salience.related_max]]


def run_ingest(
    cfg: Config,
    use_stub: bool = False,
    limit: int | None = None,
    write_files: bool = True,
    reporter: Reporter | None = None,
    full: bool = False,
) -> IngestReport:
    report = IngestReport()
    rep = reporter or ConsoleReporter()
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with rep:
        rep.set_context(corpus=str(cfg.paths.raw_dir))

        # 1. discover + chunk
        rep.stage("discover", "start")
        docs = discover_documents(cfg.paths.raw_dir)
        if not docs:
            rep.stage("discover", "done", "no documents found")
            rep.info(f"No raw documents found under {cfg.paths.raw_dir}")
            return report
        report.documents = len(docs)
        rep.stage("discover", "done", f"{len(docs)} documents")

        rep.stage("chunk", "start")
        all_chunks: list[Chunk] = []
        for doc in docs:
            dc = chunk_document(doc, cfg.chunking)
            all_chunks.extend(dc)
        if limit:
            all_chunks = all_chunks[:limit]
        report.chunks = len(all_chunks)
        if not all_chunks:
            rep.stage("chunk", "done", "no chunks produced")
            return report
        rep.stage("chunk", "done", f"{len(all_chunks)} chunks")

        # 2. corpus TF-IDF salience — Phase 2b tail only. Skipping is safe:
        # classification never reads the salience scores, and the Chunk
        # defaults (0.0) pass validate_frontmatter's range checks.
        tfidf = None
        if full:
            from .salience import compute_salience, fit_tfidf  # lazy: numpy

            rep.stage("salience", "start")
            tfidf = fit_tfidf(all_chunks)
            compute_salience(all_chunks, tfidf)
            rep.stage("salience", "done", "TF-IDF fitted")
        else:
            rep.stage("salience", "done", "skipped (compile mode; --full restores)")

        # 3. classification (small model)
        classifier = make_classifier(cfg, use_stub=use_stub)
        ok, msg = classifier.healthcheck()
        report.backend = type(classifier).__name__
        rep.set_context(backend=report.backend)
        rep.stage("classify", "start")
        if not ok and not use_stub:
            rep.info(f"classifier unreachable ({msg}); using low-confidence fallbacks")
        rep.classify_total(len(all_chunks))

        for c in all_chunks:
            result = classifier.classify(c)
            fallback = bool(result.pop("_fallback", None))
            if fallback:
                report.classify_fallbacks += 1
            else:
                report.classified_ok += 1
            c.chunk_type = result["chunk_type"]
            c.summary = result["summary"]
            c.topics = result["topics"]
            c.aliases = result["aliases"]
            c.goal_affinity = result["goal_affinity"]
            c.utility = result["utility"]
            c.authority = result["authority"]
            c.confidence = result["confidence"]
            c.standalone = result["standalone"]
            rep.classify_step(c.chunk_id, c.chunk_type, c.confidence, fallback)
        rep.stage(
            "classify", "done",
            f"{report.classified_ok} ok / {report.classify_fallbacks} fallback",
        )

        # 4. relations + index + assemble + validate + write chunk files.
        # related_chunks and the categorical index are Phase 2b tail; the
        # compile path writes a minimal index.json whose only load-bearing
        # key is `backend` (the exporter's source.stub provenance).
        md_text = ""
        if full:
            from .index_builder import build_index  # lazy: numpy

            rep.stage("index", "start")
            _compute_related(all_chunks, cfg)
            index_data = build_index(all_chunks, tfidf, cfg, created_at)
            report.entries = index_data["corpus_stats"]["total_entries"]
            md_text = index_data.pop("_md_text", "")
        else:
            rep.stage("index", "done", "skipped (compile mode; --full restores)")
            index_data = {
                "generated_at": created_at,
                "corpus_stats": {
                    "total_documents": report.documents,
                    "total_chunks": report.chunks,
                    "total_entries": 0,
                },
            }

        for c in all_chunks:
            c.frontmatter = assemble_frontmatter(c, cfg, created_at)
            report.validation_problems.extend(validate_frontmatter(c.frontmatter))
        rep.note_validation(len(report.validation_problems))

        if write_files:
            for c in all_chunks:
                write_chunk_file(c, cfg.paths.chunks_dir)

        # Record which classifier built this corpus so the exporter can stamp
        # source.stub from disk instead of trusting an operator-supplied flag.
        # This write happens in BOTH modes — it's the one load-bearing part of
        # index.json for the pack contract.
        index_data["backend"] = report.backend
        cfg.paths.index_json.parent.mkdir(parents=True, exist_ok=True)
        cfg.paths.index_json.write_text(
            json.dumps(index_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if full:
            cfg.paths.index_md.write_text(md_text, encoding="utf-8")
            rep.stage("index", "done", f"{report.entries} entries")

        # 5. Chroma upsert — Phase 2b tail. The compile path never pays the
        # chromadb import + MiniLM ONNX embedding cost: no exported field is
        # (or may be) a vector.
        if full:
            rep.stage("chroma", "start")
            from .chroma_writer import ChromaWriter  # lazy import: chromadb is heavy

            writer = ChromaWriter(cfg)
            writer.upsert_chunks(all_chunks)
            report.chroma_count = writer.count()
            rep.stage("chroma", "done", f"{report.chroma_count} vectors")
        else:
            rep.stage("chroma", "done", "skipped (compile mode; --full restores)")

    return report
