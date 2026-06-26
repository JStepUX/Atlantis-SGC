#!/usr/bin/env bash
# schema-dump.sh — Atlantis data schema: frontmatter spec, config, Chroma collections
# Usage: bash scripts/agent/schema-dump.sh
# (Repurposed from the AIX default Drizzle/API-route dump — Atlantis has no SQL
#  schema or HTTP routes; its "schema" is the YAML frontmatter + the Chroma store.)

source "$(dirname "$0")/_common.sh"
cd "$PROJECT_ROOT"

header "Schema Dump"

# ── Frontmatter schema spec ──
subheader "Salience frontmatter schema"
if [ -f atlantis-salience-schema-v1.md ]; then
  echo "  atlantis-salience-schema-v1.md"
  grep -nE '^(## |chunk_type:|utility:|status:|decay_class:|source_type:|authority:)' \
    atlantis-salience-schema-v1.md | head -25 | sed 's/^/    /'
else
  dim "  (schema spec not found)"
fi

# ── Pipeline configuration ──
subheader "Pipeline config (config/atlantis.toml)"
if [ -f config/atlantis.toml ]; then
  grep -vE '^\s*#|^\s*$' config/atlantis.toml | sed 's/^/  /'
else
  dim "  (config/atlantis.toml not found)"
fi

# ── Chroma store ──
subheader "Chroma collections"
"$PY" - <<'PY' 2>/dev/null || dim "  (chromadb unavailable or no DB yet — run 'python -m atlantis ingest')"
from atlantis.config import load_config
import chromadb
cfg = load_config()
p = cfg.paths.chroma_dir
if not p.exists():
    print(f"  (no Chroma DB at {p} — run ingest first)")
    raise SystemExit
client = chromadb.PersistentClient(path=str(p))
cols = client.list_collections()
if not cols:
    print("  (DB exists but has no collections)")
for c in cols:
    col = client.get_collection(c.name)
    n = col.count()
    print(f"  • {c.name}: {n} vectors")
    if n:
        sample = col.get(limit=1, include=["metadatas"])
        metas = sample.get("metadatas") or []
        if metas:
            keys = ", ".join(sorted(metas[0].keys()))
            print(f"      metadata keys: {keys}")
PY

echo ""
dim "Schema dump complete"
