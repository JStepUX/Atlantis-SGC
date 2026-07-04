"""Atlantis CLI — the brain-pack compiler for the sibling SGC repo.

The working loop:

  python -m atlantis ingest --stub     # raw docs -> chunk files (no model)
  python -m atlantis ingest            # same, with KoboldCPP enrichment
  (hand-edit aliases/frontmatter in Data/chunks/*.md as needed)
  python -m atlantis export --out pack.json --archive   # chunks -> pack, corpus retired
  python -m atlantis doctor            # pack-readiness + environment check

Dormant Phase 2b infrastructure (not part of the pack contract):

  python -m atlantis ingest --full     # + TF-IDF salience, index, Chroma/MiniLM
  python -m atlantis query "kimura grip"   # probe the Chroma collection (--full builds only)
"""

from __future__ import annotations

import argparse
import json
import sys

from .config import load_config


def _cmd_ingest(args) -> int:
    from .pipeline import run_ingest
    from .reporting import make_reporter

    cfg = load_config(args.config)
    reporter = make_reporter(plain=args.plain, corpus=str(cfg.paths.raw_dir))
    report = run_ingest(
        cfg,
        use_stub=args.stub,
        limit=args.limit,
        write_files=not args.no_files,
        reporter=reporter,
        full=args.full,
    )
    print("\n=== Ingest summary ===")
    print(f"  backend           : {report.backend}")
    print(f"  documents         : {report.documents}")
    print(f"  chunks            : {report.chunks}")
    print(f"  classified ok     : {report.classified_ok}")
    print(f"  classify fallbacks: {report.classify_fallbacks}")
    print(f"  validation issues : {len(report.validation_problems)}")
    if args.full:
        print(f"  index entries     : {report.entries}")
        print(f"  chroma collection : {report.chroma_count} vectors")
    if report.validation_problems:
        print("  --- validation problems (up to 10) ---")
        for p in report.validation_problems[:10]:
            print(f"    ! {p}")
    return 1 if report.validation_problems else 0


def _cmd_query(args) -> int:
    from .chroma_writer import ChromaWriter

    cfg = load_config(args.config)
    writer = ChromaWriter(cfg)
    if writer.count() == 0:
        print("Collection is empty. Run `python -m atlantis ingest --full` first (the default compile-mode ingest skips Chroma).")
        return 1
    res = writer.query(args.text, n=args.n)
    ids = res["ids"][0]
    metas = res["metadatas"][0]
    dists = res.get("distances", [[None] * len(ids)])[0]
    print(f"Top {len(ids)} for: {args.text!r}\n")
    for cid, meta, dist in zip(ids, metas, dists):
        score = f"{1 - dist:.3f}" if dist is not None else "n/a"
        print(f"[{score}] {cid}")
        print(f"        type={meta.get('chunk_type')} utility={meta.get('utility')} "
              f"path={meta.get('topic_path')}")
        print(f"        conf={meta.get('provenance_confidence')} "
              f"distinct={meta.get('salience_lexical_dist')} "
              f"dense={meta.get('salience_info_density')}")
        print()
    return 0


def _cmd_doctor(args) -> int:
    """Pack-readiness first; the Phase 2b stack is reported, never required."""
    cfg = load_config(args.config)
    print("=== Atlantis doctor ===")
    print(f"project root : {cfg.root}")
    print(f"raw_dir      : {cfg.paths.raw_dir}  (exists={cfg.paths.raw_dir.exists()})")
    print(f"chunks_dir   : {cfg.paths.chunks_dir}  (exists={cfg.paths.chunks_dir.exists()})")

    # Compile-path dependencies — these gate the exit code.
    deps_ok = True
    for mod in ("yaml",):
        try:
            __import__(mod)
            print(f"  dep {mod:<10}: ok  (compile path)")
        except ImportError as e:
            deps_ok = False
            print(f"  dep {mod:<10}: MISSING ({e})  (compile path — required)")

    # Pack readiness: chunk files to export + the provenance stamp.
    chunk_count = (
        len(list(cfg.paths.chunks_dir.glob("*.md"))) if cfg.paths.chunks_dir.exists() else 0
    )
    print(f"chunk files  : {chunk_count} in chunks_dir (export reads these)")
    from .export import read_backend_stub

    if cfg.paths.index_json.exists():
        stub = read_backend_stub(cfg.paths.index_json)
        print(f"index.json   : present — backend stamp -> packs export as stub={stub}")
    else:
        print("index.json   : MISSING — run ingest; without it packs export as stub=false")

    # raw doc count
    from .chunking import discover_documents

    docs = discover_documents(cfg.paths.raw_dir)
    print(f"raw documents: {len(docs)} found")

    # Optional enrichment (KoboldCPP classification) — informative only:
    # --stub compiles packs with no model at all.
    from .classify import KoboldClassifier

    ok, msg = KoboldClassifier(cfg).healthcheck()
    print(f"model        : {'ok' if ok else 'unreachable'} -> {msg}")
    print(f"               ({cfg.model.model} @ {cfg.model.base_url}; optional — --stub needs no model)")

    # Dormant Phase 2b stack (--full ingests only) — informative only.
    for mod in ("numpy", "chromadb", "requests"):
        try:
            __import__(mod)
            print(f"  dep {mod:<10}: ok  (--full / enrichment only)")
        except ImportError:
            print(f"  dep {mod:<10}: absent  (fine unless using --full{' or KoboldCPP' if mod == 'requests' else ''})")

    return 0 if deps_ok else 1


def _cmd_export(args) -> int:
    from datetime import datetime, timezone
    from pathlib import Path

    from .export import build_pack, read_backend_stub, validate_pack, write_pack
    from .textutils import slugify

    cfg = load_config(args.config)
    out_path = Path(args.out)
    pack_id = args.id or slugify(out_path.stem)
    stub = read_backend_stub(cfg.paths.index_json)
    built_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    pack = build_pack(
        cfg.paths.chunks_dir,
        pack_id=pack_id,
        name=args.name or pack_id,
        description=args.description or "",
        version=args.pack_version,
        stub=stub,
        built_at=built_at,
    )
    if not args.description:
        docs = {c["source"]["doc"] for c in pack["chunks"]}
        pack["description"] = (
            f"{len(docs)} documents / {len(pack['chunks'])} chunks "
            f"exported from Atlantis"
        )

    problems = validate_pack(pack)
    print("=== Export summary ===")
    print(f"  chunks dir : {cfg.paths.chunks_dir}")
    print(f"  pack id    : {pack['id']}  (name: {pack['name']})")
    print(f"  chunks     : {len(pack['chunks'])}")
    print(f"  stub build : {pack['source']['stub']}")
    if problems:
        print("  --- problems (pack NOT written) ---")
        for p in problems[:10]:
            print(f"    ! {p}")
        return 1
    write_pack(pack, out_path)
    print(f"  written    : {out_path}")

    # --archive: retire the corpus only AFTER a successful pack write, so a
    # failed export never eats the sources it failed to export.
    if args.archive:
        from .export import archive_build

        dest = archive_build(
            raw_dir=cfg.paths.raw_dir,
            chunks_dir=cfg.paths.chunks_dir,
            index_json=cfg.paths.index_json,
            index_md=cfg.paths.index_md,
            pack_path=out_path,
            archive_root=cfg.paths.archive_dir,
            pack_id=pack["id"],
            built_at=built_at,
        )
        print(f"  archived   : {dest}")
        print("               (raw + chunks + index.json moved, pack copied — working dirs clean for the next brain)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="atlantis", description="Atlantis salience pipeline")
    parser.add_argument("--config", default=None, help="path to atlantis.toml")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ing = sub.add_parser("ingest", help="process raw docs into chunk files (the export source)")
    p_ing.add_argument("--stub", action="store_true", help="offline classifier (no model)")
    p_ing.add_argument("--limit", type=int, default=None, help="process only N chunks")
    p_ing.add_argument(
        "--no-files",
        action="store_true",
        help="skip writing chunk .md files (NOTE: export reads those files — a --no-files ingest produces nothing to export)",
    )
    p_ing.add_argument("--plain", action="store_true", help="plain log instead of the live dashboard")
    p_ing.add_argument(
        "--full",
        action="store_true",
        help="also run the dormant Phase 2b tail: TF-IDF salience, categorical index, Chroma/MiniLM upsert",
    )
    p_ing.set_defaults(func=_cmd_ingest)

    p_q = sub.add_parser("query", help="probe the Chroma collection (Phase 2b; needs a --full ingest)")
    p_q.add_argument("text", help="query text")
    p_q.add_argument("-n", type=int, default=5, help="number of results")
    p_q.set_defaults(func=_cmd_query)

    p_doc = sub.add_parser("doctor", help="pack-readiness + environment check")
    p_doc.set_defaults(func=_cmd_doctor)

    p_exp = sub.add_parser("export", help="export chunks as an sgc-brain/1 knowledge pack")
    p_exp.add_argument("--out", required=True, help="output .json path (stem = default pack id)")
    p_exp.add_argument("--id", default=None, help="pack id [a-z0-9-]{1,64}")
    p_exp.add_argument("--name", default=None, help="display name")
    p_exp.add_argument("--description", default=None, help="pack description")
    p_exp.add_argument("--pack-version", default="1.0", help="pack author's version string")
    p_exp.add_argument(
        "--archive",
        action="store_true",
        help="after a successful export, retire the corpus: move raw docs, chunk files, and "
        "index.json into <archive_dir>/<pack-id>_<stamp>/ with a copy of the pack — "
        "clean slate for the next brain (skip this flag to keep re-exporting the same corpus)",
    )
    p_exp.set_defaults(func=_cmd_export)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
