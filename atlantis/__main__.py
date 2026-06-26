"""Atlantis CLI.

  python -m atlantis ingest            # full pipeline: raw -> chunks -> Chroma
  python -m atlantis ingest --stub     # offline (no model) end-to-end dry run
  python -m atlantis ingest --limit 5  # only the first 5 chunks
  python -m atlantis query "kimura grip"   # sanity-check retrieval
  python -m atlantis doctor            # check config, model reachability, deps
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
    )
    print("\n=== Ingest summary ===")
    print(f"  backend           : {report.backend}")
    print(f"  documents         : {report.documents}")
    print(f"  chunks            : {report.chunks}")
    print(f"  index entries     : {report.entries}")
    print(f"  classified ok     : {report.classified_ok}")
    print(f"  classify fallbacks: {report.classify_fallbacks}")
    print(f"  validation issues : {len(report.validation_problems)}")
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
        print("Collection is empty. Run `python -m atlantis ingest` first.")
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
    cfg = load_config(args.config)
    print("=== Atlantis doctor ===")
    print(f"project root : {cfg.root}")
    print(f"raw_dir      : {cfg.paths.raw_dir}  (exists={cfg.paths.raw_dir.exists()})")
    print(f"chroma_dir   : {cfg.paths.chroma_dir}")
    print(f"model        : {cfg.model.model} @ {cfg.model.base_url}")

    # dependency check
    deps_ok = True
    for mod in ("chromadb", "numpy", "yaml", "requests"):
        try:
            __import__(mod)
            print(f"  dep {mod:<10}: ok")
        except ImportError as e:
            deps_ok = False
            print(f"  dep {mod:<10}: MISSING ({e})")

    # model reachability
    from .classify import KoboldClassifier

    ok, msg = KoboldClassifier(cfg).healthcheck()
    print(f"model        : {'ok' if ok else 'UNREACHABLE'} -> {msg}")

    # raw doc count
    from .chunking import discover_documents

    docs = discover_documents(cfg.paths.raw_dir)
    print(f"raw documents: {len(docs)} found")
    return 0 if deps_ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="atlantis", description="Atlantis salience pipeline")
    parser.add_argument("--config", default=None, help="path to atlantis.toml")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ing = sub.add_parser("ingest", help="process raw docs into chunks + Chroma")
    p_ing.add_argument("--stub", action="store_true", help="offline classifier (no model)")
    p_ing.add_argument("--limit", type=int, default=None, help="process only N chunks")
    p_ing.add_argument("--no-files", action="store_true", help="skip writing chunk .md files")
    p_ing.add_argument("--plain", action="store_true", help="plain log instead of the live dashboard")
    p_ing.set_defaults(func=_cmd_ingest)

    p_q = sub.add_parser("query", help="query the Chroma collection")
    p_q.add_argument("text", help="query text")
    p_q.add_argument("-n", type=int, default=5, help="number of results")
    p_q.set_defaults(func=_cmd_query)

    p_doc = sub.add_parser("doctor", help="check environment, deps, model")
    p_doc.set_defaults(func=_cmd_doctor)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
