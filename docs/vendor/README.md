# Vendored Documentation

Hand-written API reference for packages that sit beyond the agent's training cutoff, kept in-repo so agents have accurate docs at the call site instead of hallucinating from stale memory.

- `reference/*.md` — durable per-package reference (currently React 19, Tailwind v4, Drizzle 0.45, Anthropic SDK 0.90).
- Surfaced by `bash scripts/agent/read-docs.sh <package>` (and `--index` / `--audit`). The `VENDORED_DOCS` map in that script is the registry — when you add a reference doc here, add it to the map or the audit won't see it.
- Full rationale and the coverage tiers (vendored / Context7 / flying blind) live in `CLAUDE.md` → "Working Outside Training Data."

Add a doc here when a package is touched often enough that round-tripping to Context7 every time is wasteful.
