"""Offline smoke test for the Atlantis pipeline.

Runs the full ingest in stub mode (no model required) against the bundled
fixtures, into a throwaway temp directory, and asserts the output is schema-valid.

Run directly:        python tests/test_pipeline.py
Or under pytest:     pytest tests/test_pipeline.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

# Make the package importable when run as a plain script.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from atlantis.config import load_config  # noqa: E402
from atlantis.pipeline import run_ingest  # noqa: E402
from atlantis.reporting import NullReporter  # noqa: E402
from atlantis.schema import validate_frontmatter  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _make_config(tmp: Path):
    cfg = load_config()  # defaults
    cfg.paths.raw_dir = FIXTURES
    cfg.paths.chunks_dir = tmp / "chunks"
    cfg.paths.chroma_dir = tmp / "chroma"
    cfg.paths.index_json = tmp / "index.json"
    cfg.paths.index_md = tmp / "index.md"
    cfg.index.root_min_count = 2
    cfg.index.root_min_distinct = 2
    return cfg


def test_stub_ingest_compile_mode_is_schema_valid():
    # The DEFAULT ingest: the lean compile path. No salience, no index build,
    # no Chroma — but chunk files land, validation runs, and index.json still
    # carries the backend stamp (the exporter's stub-provenance source).
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        tmp = Path(td)
        cfg = _make_config(tmp)
        report = run_ingest(
            cfg, use_stub=True, write_files=True, reporter=NullReporter()
        )

        assert report.documents == 3, report.documents
        assert report.chunks > 0, report.chunks
        assert report.validation_problems == [], report.validation_problems
        # The Phase 2b tail did not run.
        assert report.chroma_count == 0
        assert report.entries == 0
        assert not (tmp / "chroma").exists()
        assert not (tmp / "index.md").exists()
        # The load-bearing artifacts did.
        import json
        index = json.loads((tmp / "index.json").read_text(encoding="utf-8"))
        assert index["backend"] == "StubClassifier"

        # Every emitted chunk file re-validates from disk.
        chunk_files = list((tmp / "chunks").glob("*.md"))
        assert len(chunk_files) == report.chunks
        for f in chunk_files:
            assert f.read_text(encoding="utf-8").startswith("---\n")


def test_stub_ingest_full_mode_runs_the_phase2b_tail():
    # --full restores the original vector pipeline end-to-end.
    # ignore_cleanup_errors: Chroma keeps the HNSW/SQLite file handles open for
    # the life of the process, so Windows can't delete the temp dir on exit.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        tmp = Path(td)
        cfg = _make_config(tmp)
        report = run_ingest(
            cfg, use_stub=True, write_files=True, reporter=NullReporter(), full=True
        )

        assert report.documents == 3, report.documents
        assert report.chunks > 0, report.chunks
        assert report.validation_problems == [], report.validation_problems
        assert report.chroma_count == report.chunks
        assert (tmp / "index.json").exists()
        assert (tmp / "index.md").exists()
        assert len(list((tmp / "chunks").glob("*.md"))) == report.chunks


def test_topic_path_and_specificity_derivation():
    from atlantis.schema import derive_specificity, derive_topic_path

    topics = [
        {"topic": "kimura", "depth": 0},
        {"topic": "bjj", "depth": 2},
        {"topic": "grip", "depth": 0},
    ]
    assert derive_topic_path(topics) == "kimura.grip.bjj"
    assert derive_specificity(topics) == round(2 / 3, 3)


def test_scrub_brackets_unit():
    from atlantis.textutils import scrub_brackets

    # Wikipedia-style citation markers, editorial tags, and a note ref.
    src = "The kimura[1] is a lock.[12][note 3] See [edit] more [citation needed] here."
    assert scrub_brackets(src) == "The kimura is a lock. See more here."
    # Markdown link labels (Confluence import output) survive intact.
    assert scrub_brackets("Keep [this](http://x) drop [4].") == "Keep [this](http://x) drop."
    # Nested groups peel to nothing; newlines are never swallowed.
    assert scrub_brackets("a\n[[Category:X]]\nb") == "a\n\nb"
    # Idempotent and deterministic.
    once = scrub_brackets(src)
    assert scrub_brackets(once) == once


def test_ingest_scrubs_bracket_noise_end_to_end():
    from atlantis.chunking import discover_documents

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        raw = tmp / "raw"
        raw.mkdir()
        (raw / "wiki-paste.md").write_text(
            "# Kimura (grappling)[edit]\n\n"
            "The kimura[1][2] is a double joint lock.[citation needed] "
            "It targets the shoulder [a] and elbow.[3]\n\n"
            "See [the guide](http://example.test/guide) for more.[4]\n",
            encoding="utf-8",
        )
        docs = discover_documents(raw)
        assert len(docs) == 1
        assert docs[0].title == "Kimura (grappling)"
        assert "[" not in docs[0].text.replace("[the guide](", "")

        cfg = _make_config(tmp)
        cfg.paths.raw_dir = raw
        run_ingest(cfg, use_stub=True, reporter=NullReporter())
        bodies = [
            p.read_text(encoding="utf-8") for p in (tmp / "chunks").rglob("*.md")
        ]
        assert bodies, "ingest wrote no chunk files"
        for chunk_file in bodies:
            # Frontmatter legitimately contains YAML lists ("related_chunks: []");
            # only the body below the closing delimiter must be bracket-free.
            body = chunk_file.split("\n---\n", 2)[-1]
            stripped = body.replace("[the guide](", "")
            assert "[" not in stripped and "]" not in stripped, body
            assert "[the guide](http://example.test/guide)" in body


if __name__ == "__main__":
    test_stub_ingest_compile_mode_is_schema_valid()
    test_stub_ingest_full_mode_runs_the_phase2b_tail()
    test_topic_path_and_specificity_derivation()
    test_scrub_brackets_unit()
    test_ingest_scrubs_bracket_noise_end_to_end()
    print("OK: all smoke tests passed")
