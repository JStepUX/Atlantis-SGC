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


if __name__ == "__main__":
    test_stub_ingest_compile_mode_is_schema_valid()
    test_stub_ingest_full_mode_runs_the_phase2b_tail()
    test_topic_path_and_specificity_derivation()
    print("OK: all smoke tests passed")
