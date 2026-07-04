"""Offline test for the brain-pack exporter.

Stub-ingests the bundled fixtures into a throwaway temp directory, exports an
sgc-brain/1 pack from the resulting chunk files, and asserts the pack is
schema-valid, deterministic, and honest about its stub provenance.

Run directly:        python tests/test_export.py
Or under pytest:     pytest tests/test_export.py
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

# Make the package importable when run as a plain script.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from atlantis.config import load_config  # noqa: E402
from atlantis.export import (  # noqa: E402
    archive_build,
    build_pack,
    flatten_aliases,
    parse_chunk_file,
    read_backend_stub,
    validate_pack,
    write_pack,
)
from atlantis.pipeline import run_ingest  # noqa: E402
from atlantis.reporting import NullReporter  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
BUILT_AT = "2026-07-04T00:00:00Z"


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


def _build(cfg) -> dict:
    return build_pack(
        cfg.paths.chunks_dir,
        pack_id="fixture-pack",
        name="Fixture Pack",
        description="stub-built fixture corpus",
        version="1.0",
        stub=read_backend_stub(cfg.paths.index_json),
        built_at=BUILT_AT,
    )


def test_stub_export_is_pack_valid():
    # ignore_cleanup_errors: Chroma keeps file handles open for the life of
    # the process, so Windows can't delete the temp dir on exit.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        tmp = Path(td)
        cfg = _make_config(tmp)
        report = run_ingest(cfg, use_stub=True, write_files=True, reporter=NullReporter())
        assert report.chunks > 0, report.chunks

        # Ingest stamps the classifier backend so export can prove stub-ness.
        assert read_backend_stub(cfg.paths.index_json) is True

        pack = _build(cfg)
        assert validate_pack(pack) == [], validate_pack(pack)
        assert pack["schema"] == "sgc-brain/1"
        assert pack["source"] == {
            "tool": "atlantis",
            "schema": "atlantis-salience-v1",
            "stub": True,
        }
        assert len(pack["chunks"]) == report.chunks
        assert {c["source"]["doc"] for c in pack["chunks"]} == {
            "kimura-grip-mechanics",
            "minnesota-facts",
            "couscous-recipe",
        }

        for c in pack["chunks"]:
            assert 1 <= len(c["text"]) <= 8000, c["id"]
            assert c["title"], c["id"]
            assert c["summary"], c["id"]
            assert isinstance(c["topics"], list) and c["topics"], c["id"]
            assert isinstance(c["aliases"], list), c["id"]
            assert isinstance(c["tokens"], int) and c["tokens"] >= 0, c["id"]
            assert isinstance(c["source"]["position"], int), c["id"]

        # Determinism: same chunk files + same built_at -> identical pack.
        assert _build(cfg) == pack

        # Round-trip: written file is valid UTF-8 JSON.
        out = tmp / "pack.json"
        write_pack(pack, out)
        assert json.loads(out.read_text(encoding="utf-8")) == pack


def test_missing_index_json_defaults_to_not_stub():
    # No index.json -> conservative provenance: never claim model-free falsely.
    assert read_backend_stub(Path("does/not/exist/index.json")) is False


CHUNK_TEMPLATE = """---
chunk_id: {cid}
document_slug: demo-doc
source_file: Data/raw/demo.md
document_title: Demo Document
summary: A demo chunk.
topics:
- topic: demo
  depth: 0
aliases:
  ude-garami: hammerlock
navigation:
  current: 0
  total: 1
  next: null
  previous: null
status: {status}
tokens: 12
---

{body}
"""


def test_fence_in_body_and_status_filter_and_aliases():
    with tempfile.TemporaryDirectory() as td:
        chunks = Path(td) / "chunks"
        chunks.mkdir()
        body = "First line.\n\n---\n\nText after an hrule fence inside the body."
        (chunks / "demo-doc_000.md").write_text(
            CHUNK_TEMPLATE.format(cid="demo-doc_000", status="active", body=body),
            encoding="utf-8",
        )
        (chunks / "demo-doc_001.md").write_text(
            CHUNK_TEMPLATE.format(cid="demo-doc_001", status="draft", body="Draft text."),
            encoding="utf-8",
        )

        # The body's own --- must not truncate the parse.
        fm, parsed_body = parse_chunk_file(chunks / "demo-doc_000.md")
        assert parsed_body == body
        assert fm["chunk_id"] == "demo-doc_000"

        # Aliases flatten keys AND values, in order.
        assert flatten_aliases(fm["aliases"]) == ["ude-garami", "hammerlock"]
        assert flatten_aliases({}) == []
        assert flatten_aliases(None) == []

        # Only status: active chunks are exported.
        pack = build_pack(
            chunks,
            pack_id="demo",
            name="Demo",
            description="d",
            version="1.0",
            stub=True,
            built_at=BUILT_AT,
        )
        assert [c["id"] for c in pack["chunks"]] == ["demo-doc_000"]
        assert pack["chunks"][0]["text"] == body
        assert pack["chunks"][0]["aliases"] == ["ude-garami", "hammerlock"]
        assert validate_pack(pack) == []


def test_export_archive_retires_the_corpus():
    import shutil

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        tmp = Path(td)
        cfg = _make_config(tmp)
        # --archive MOVES the raw docs, so ingest from a disposable COPY of
        # the fixtures — never the originals.
        cfg.paths.raw_dir = tmp / "raw"
        shutil.copytree(FIXTURES, cfg.paths.raw_dir)
        cfg.paths.archive_dir = tmp / "archive"
        run_ingest(cfg, use_stub=True, write_files=True, reporter=NullReporter())

        pack = _build(cfg)
        out = tmp / "my-brain.json"
        write_pack(pack, out)

        kwargs = dict(
            raw_dir=cfg.paths.raw_dir,
            chunks_dir=cfg.paths.chunks_dir,
            index_json=cfg.paths.index_json,
            index_md=cfg.paths.index_md,
            pack_path=out,
            archive_root=cfg.paths.archive_dir,
            pack_id=pack["id"],
            built_at=BUILT_AT,
        )
        dest = archive_build(**kwargs)

        # The bundle is self-contained: sources + chunks + provenance + pack copy.
        assert (dest / "my-brain.json").exists()
        assert len(list((dest / "raw").iterdir())) == 3
        assert len(list((dest / "chunks").glob("*.md"))) == len(pack["chunks"])
        assert (dest / "index.json").exists()

        # Working dirs are emptied but present; the stamp left with its build.
        assert list(cfg.paths.raw_dir.iterdir()) == []
        assert list(cfg.paths.chunks_dir.iterdir()) == []
        assert not cfg.paths.index_json.exists()
        # The pack at --out is untouched (the archive holds a COPY).
        assert out.exists()

        # Exporting from the now-clean slate fails loudly, never silently
        # builds an empty pack — the mistake the flag exists to prevent.
        empty = build_pack(
            cfg.paths.chunks_dir,
            pack_id="again", name="n", description="d", version="1",
            stub=False, built_at=BUILT_AT,
        )
        assert any("no active chunks" in p for p in validate_pack(empty))

        # Same id + stamp again -> a suffixed sibling, never an overwrite.
        dest2 = archive_build(**kwargs)
        assert dest2 != dest
        assert dest2.name.startswith(pack["id"])


def test_validate_pack_catches_contract_breaks():
    base = {
        "schema": "sgc-brain/1",
        "id": "ok-pack",
        "name": "n",
        "description": "d",
        "version": "1",
        "built_at": BUILT_AT,
        "source": {"tool": "atlantis", "schema": "atlantis-salience-v1", "stub": True},
        "chunks": [
            {
                "id": "c_000",
                "title": "t",
                "text": "body",
                "summary": "s",
                "topics": ["demo"],
                "aliases": [],
                "source": {"file": "f", "doc": "d", "position": 0},
                "tokens": 1,
            }
        ],
    }
    assert validate_pack(base) == []

    bad_schema = dict(base, schema="sgc-brain/2")
    assert any("bad schema" in p for p in validate_pack(bad_schema))

    bad_id = dict(base, id="Not Valid!")
    assert any("not [a-z0-9-]" in p for p in validate_pack(bad_id))

    empty = dict(base, chunks=[])
    assert any("no active chunks" in p for p in validate_pack(empty))

    long_text = dict(base, chunks=[dict(base["chunks"][0], text="x" * 8001)])
    assert any("outside 1..8000" in p for p in validate_pack(long_text))

    dupes = dict(base, chunks=[base["chunks"][0], dict(base["chunks"][0])])
    assert any("duplicate chunk id" in p for p in validate_pack(dupes))


if __name__ == "__main__":
    test_stub_export_is_pack_valid()
    test_missing_index_json_defaults_to_not_stub()
    test_fence_in_body_and_status_filter_and_aliases()
    test_export_archive_retires_the_corpus()
    test_validate_pack_catches_contract_breaks()
    print("OK: all export tests passed")
