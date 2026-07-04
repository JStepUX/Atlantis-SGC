If you ever encounter something in the project that surprises you, please alert the developer working with you and indicate that this is the case in the AGENTS.md file to help prevent future agents from having the same issue.

## What this is

**Atlantis** is the offline **brain-pack compiler** for the sibling SGC repo
(`D:/Bolt-On/sgc`): it processes raw documents into frontmatter-annotated chunk
files (the [Atlantis Salience Schema v1.0](atlantis-salience-schema-v1.md)) and
**exports them as `sgc-brain/1` knowledge packs** that SGC mounts per chat.
Only lexical fields cross that contract — text, summary, topics, hand-editable
aliases — never embeddings. The original Chroma/vector tail is retained as
**dormant Phase 2b infrastructure** (`ingest --full`) for a future
embeddings-vs-lexical retrieval comparison; it is not the mission. Atlantis also
carries the **AIX process layer** (agent fleet in `.claude/agents/`, skills in
`.claude/skills/`, the pre-commit gate in `.claude/hooks/`, documentation
conventions in `docs/`, and agent utility scripts in `scripts/agent/`).

The guiding principle is **pepper instructions at the point of discovery, not in
always-on context.** This file stays lean. Detailed conventions live next to what
they govern: each `docs/` subdirectory has a `README.md` describing its own rules
— read it before writing into that directory. Skills carry their own procedures
and load when triggered.

## Project identity

Atlantis is a single Python package, `atlantis/`, driven by a CLI
(`python -m atlantis <ingest|export|doctor|query>`). The default ingest is the
**compile path**: **discover → chunk → classify → assemble → write chunk
files → stamp `backend` into index.json** (see `atlantis/pipeline.py`).
Chunking is deterministic; only the **classification** stage may call a model —
a local **KoboldCPP / Gemma** server (`config/atlantis.toml [model]`), or the
fully-offline `--stub` classifier (packs then carry honest `stub: true`
provenance, read from index.json's `backend` stamp). `export` maps active
chunks onto an `sgc-brain/1` pack (`atlantis/export.py`) — lexical fields only.
Raw inputs go in `Data/raw/`; chunk files in `Data/chunks/` are hand-editable
(aliases especially — the pack's synonym bridge) and are **overwritten by
re-ingest**, so edit-then-export, and re-ingest only when sources change.
`ingest --full` additionally runs the dormant Phase 2b tail (TF-IDF salience →
categorical index → Chroma/MiniLM), whose outputs never reach a pack.

## Stack

- **Language:** Python 3.11+ (developed on 3.14).
- **Compile path:** PyYAML (frontmatter — the only hard dependency),
  tomllib (stdlib, config), requests (only for non-stub KoboldCPP enrichment).
- **Dormant Phase 2b tail** (`ingest --full` only, lazily imported): chromadb
  (ONNX `all-MiniLM-L6-v2` embeddings) + numpy (TF-IDF salience/index). A
  compile-only environment can omit both.
- **Classification model (optional):** local KoboldCPP server (Gemma),
  OpenAI-compatible API; `--stub` compiles packs with no model at all.
- **Tests:** `tests/test_pipeline.py` + `tests/test_export.py` (pytest-
  compatible; pytest not required). Run with `python tests/<file>`.
- The `anthropic` SDK is installed in the environment but the pipeline does not
  use it — classification goes through KoboldCPP.

## Agent Utility Scripts (`scripts/agent/`) — CHECK THESE BEFORE MULTI-STEP TOOL CALLS

Bash scripts that collapse common multi-tool-call patterns into single
invocations. **Before chaining 3+ tool calls for file reading, import tracing,
grepping, or health checking, check if one of these already does it.** Run via
`bash scripts/agent/<script>.sh`.

> These were **reconciled from the AIX default (TypeScript) stack to Python** at
> install time. Import/signature extraction uses Python's `ast` module;
> `schema-dump.sh` was repurposed (Atlantis has no SQL/HTTP layer);
> `read-docs.sh` tracks the Python deps. There is no `health-check`/`test-scan`
> for `tsc`/Vitest — they target `compileall`/`ruff`/`mypy`/pytest instead.

| Script | Purpose | Usage |
|--------|---------|-------|
| `file-context.sh` | File content + resolved Python import signatures | `file-context.sh <path> [--no-imports]` |
| `codebase-snapshot.sh` | Tree, file counts, git log, deps, entrypoints | `codebase-snapshot.sh` |
| `related-files.sh` | Grep for a term + first matches per file (.py/.md/.toml) | `related-files.sh <term> [dir]` |
| `git-context.sh` | Status, diffs, branch info for commits/PRs | `git-context.sh [base-branch]` |
| `health-check.sh` | compileall + ruff/mypy (if present) + tests + git + TODO counts | `health-check.sh` |
| `trace-imports.sh` | Who imports a module/symbol (2-level) | `trace-imports.sh <module-or-symbol>` |
| `schema-dump.sh` | Frontmatter schema + config (+ Chroma stats when a --full build exists) | `schema-dump.sh` |
| `test-scan.sh` | Test gap analysis + metrics (pytest conventions) | `test-scan.sh [--scope <dir>]` |
| `extract-interfaces.sh` | Public signature extraction (ast) | `extract-interfaces.sh <file-or-dir>` |
| `read-docs.sh` | Vendored docs + Context7 pointers for post-cutoff deps | `read-docs.sh <package>` |

Shared utilities live in `_common.sh` (project root detection, colors,
`resolve_import()`, `extract_imports()`, `extract_signatures()` — all Python-aware).

## Working Outside Training Data — Read Before You Write

Some installed packages are beyond the agent's training cutoff. **Context7 MCP is
the default reference source.** Run the audit against the actual installed deps:

```bash
bash scripts/agent/read-docs.sh --audit     # installed versions vs. cutoff registry
bash scripts/agent/read-docs.sh chromadb    # familiarity + Context7 pointer for a dep
bash scripts/agent/read-docs.sh --index     # vendored docs + Context7 coverage
```

- **Vendored docs** (`docs/vendor/reference/*.md`) — none yet for this stack (the
  JS defaults were dropped at install). Vendor one and add it to the
  `VENDORED_DOCS` map in `read-docs.sh` if a dep churns enough to warrant it.
- **Context7 MCP** — chromadb, numpy, anthropic, requests, pyyaml.
- **Flying blind** — `read-docs.sh --stale` calls these out (currently
  onnxruntime, used only transitively via Chroma's default embedding function).

## Conventions

- **Tests — the smoke tests, real data over mocks.** `tests/test_pipeline.py`
  (compile mode + `--full` mode) and `tests/test_export.py` run stub-mode
  ingests against the bundled fixtures and validate the schema and the pack
  contract. Prefer real data; the only sanctioned mock-like shortcut is the
  `StubClassifier` (offline classification). Run both suites, not just the new test.
- **Verify against the pack contract, not just code inspection.** After changing
  anything that shapes chunking, classification, or the exporter, run a stub
  ingest into a scratch dir, `export` from it, and inspect the pack (field
  mapping, stub provenance, chunk texts) — that JSON is what SGC consumes.
  When the change targets non-stub enrichment specifically, also run a real
  ingest against the running KoboldCPP server and read the chunk frontmatter it
  produced. Core Value #5: build the check, don't trust the self-report.
- **Determinism.** Chunking must be reproducible across runs (same input →
  same `chunk_id`s), and export must be a pure function of the chunk files +
  the built_at stamp. The `--full` tail's TF-IDF/index scores are held to the
  same rule. Don't introduce wall-clock or RNG into those stages.

## Core Values

1. I don't want to be right; I want to do right.
2. Be kind to future you.
3. Don't build systems that require diligence. Build systems that catch you when you're not diligent.
4. Half-measures are confusing to future agents — commit fully.
5. The agent doesn't know what it doesn't know. Build the check, don't trust the self-report.
6. Let friction drive the architecture, not speculation.
7. Ship what you'd sign.

## Git & commits

- Use **bare `git` commands** (no `cd` prefix). The working directory is already correct.
- For multi-line commit messages, use a heredoc so the shell doesn't mangle the body.
- **Prefer a new commit over amending.** The one sanctioned exception is
  `release-prep`'s post-commit SHA fixup (it flags the amend in its report).
- Commit only when asked. **Solo repo — commit on `main` directly.** (This
  overrides the harness's branch-first default, same as the sibling SGC repo:
  there's no review workflow that benefits from feature branches, and stray
  branches just accumulate. The developer confirmed this convention 2026-07-04.)
- **Pre-commit gate:** `.claude/hooks/pre-commit-gate.mjs` blocks `git commit`
  until `/pre-commit-qa` has run for the current branch within the last 10
  minutes — **but only once its `PreToolUse` entry exists in
  `.claude/settings.json`.** Until that entry is added, the gate is inert. Run
  `/pre-commit-qa` before committing.
- `release-prep` bumps the version in `atlantis/__init__.py` (`__version__`),
  not a `package.json`.

## Executing actions with care

For actions that are hard to reverse or that reach outside the repo (pushing,
deploying, deleting, sending), confirm first unless the user has durably
authorized it. Approval for one step does not extend to the next. Report outcomes
faithfully: if tests fail, say so with the output; if a step was skipped, say that.
