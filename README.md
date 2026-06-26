# Atlantis Salience Pipeline

Processes raw documents into salience-annotated chunks and writes them to a
[Chroma](https://www.trychroma.com/) vector database, following the
**[Atlantis Salience Schema v1.0](atlantis-salience-schema-v1.md)**.

The structure is domain-agnostic: BJJ techniques, Minnesota trivia, Star Wars
lore, and couscous recipes all flow through the same fields — the domain lives in
the *values*, never the *field names*.

---

## Pipeline at a glance

```
Data/raw/*.md ──▶ chunk ──▶ TF-IDF salience ──▶ classify (Gemma) ──▶ relate
                                                                         │
   Chroma DB  ◀── flatten metadata ◀── assemble + validate frontmatter ◀┘
        +
   Data/index.json / index.md   (categorical index, companion artifact)
```

| Stage | Module | What it produces |
|---|---|---|
| Discover + chunk | `chunking.py` | identity, navigation, heading-aware bodies, token counts |
| Salience | `salience.py` | `lexical_distinctiveness`, `information_density` (corpus TF-IDF) |
| Classify | `classify.py` | `chunk_type`, `summary`, `topics`, `aliases`, `goal_affinity`, `utility`, `authority`, `confidence`, `standalone` |
| Relate | `pipeline.py` | `related_chunks` (cross-doc topic overlap) |
| Index | `index_builder.py` | root terms, entries, sibling similarity, `index_ref` |
| Assemble | `schema.py` | ordered frontmatter, `topic_path`, `specificity`, validation |
| Persist | `chroma_writer.py` | flattened Chroma metadata + alias-augmented embeddings |

### What is computed vs. generated

- **Atlantis (deterministic):** identity, navigation, TF-IDF salience, `topic_path`,
  `specificity`, related/index links, timestamps, token counts.
- **Small model (Gemma via KoboldCPP):** the subjective fields — `chunk_type`,
  `summary`, `topics`+depths, `aliases`, `goal_affinity`, `utility`, `authority`,
  `confidence`, `standalone`.

---

## Setup

```bash
pip install -r requirements.txt
```

Requires **Python 3.11+** (tested on 3.14). The default embedding model
(all-MiniLM-L6-v2, ~80 MB ONNX) downloads automatically on first ingest.

The classification step talks to a local **KoboldCPP** server over its
OpenAI-compatible API. Defaults assume `http://localhost:5001/v1` — change in
`config/atlantis.toml` if needed. You can run the whole pipeline **without** a
model using `--stub` (see below).

---

## Usage

```bash
# 1. Drop documents into Data/raw/ (.md, .markdown, .txt — subdirs scanned recursively)

# 2. Check environment, dependencies, and model reachability
python -m atlantis doctor

# 3. Full ingest: raw docs -> chunks -> Chroma
python -m atlantis ingest

# Offline dry run (no model; deterministic placeholder classification)
python -m atlantis ingest --stub

# Process only the first N chunks (fast iteration while tuning)
python -m atlantis ingest --limit 5

# Plain line-by-line log instead of the live dashboard
python -m atlantis ingest --plain

# Sanity-check retrieval against the built collection
python -m atlantis query "how do I break a grip" -n 5
```

Re-running `ingest` **upserts** by `chunk_id`, so it is idempotent — edit a
source doc and re-run without duplicating vectors.

### Watching it run

On an interactive terminal, `ingest` shows a live dashboard. The slow stage is
**Classify** (one model call per chunk, run sequentially), so it gets a progress
bar with a live ETA:

```
Atlantis Ingest  ·  Data/raw  ·  KoboldClassifier
──────────────────────────────────────────────────
  ✔  Discover  12 documents
  ✔  Chunk     487 chunks
  ✔  Salience  TF-IDF fitted
  ◐  Classify  ━━━━━━━━━━╸···········  213/487  44%
              elapsed 3:12  ·  eta 4:06
  ·  Index     waiting
  ·  Chroma    waiting
──────────────────────────────────────────────────
  ▸ kimura-grip-mechanics_003  procedure  conf 0.95
  validation: 0 issues    fallbacks: 0
```

The dashboard auto-falls back to a plain log when output is piped/redirected or
the terminal isn't a TTY. On legacy Windows code pages it uses an ASCII glyph set
(`#`/`-`/`*`) instead of the box-drawing characters. Force the plain log anytime
with `--plain`. The event layer (`atlantis/reporting.py`) is UI-agnostic, so a web
frontend could later consume the same `Reporter` interface.

### Outputs

| Path | What |
|---|---|
| `Data/chunks/<chunk_id>.md` | Human-inspectable chunk = frontmatter + body |
| `Data/chroma/` | Persistent Chroma DB (the retrieval target) |
| `Data/index.json` | Machine-readable categorical index |
| `Data/index.md` | Human-readable index (its line numbers feed `index_ref.line`) |

---

## Configuration

All knobs live in [`config/atlantis.toml`](config/atlantis.toml). Highlights:

- `[chunking]` — `target_tokens` / `max_tokens` / `min_tokens` and heading-respect.
- `[model]` — KoboldCPP `base_url`, `model`, temperature, timeout, retries.
- `[embeddings]` — collection name and `alias_strategy` (`append`/`prepend`/`none`).
- `[index]` — root-term thresholds and `sibling_threshold` (the schema's two
  empirical open questions — tune against your corpus).
- `[provenance]` / `[temporal]` — defaults for `source_type`, `decay_class`, etc.

Override the config path for any command: `--config path/to/other.toml`.

---

## Testing

```bash
python tests/test_pipeline.py      # offline smoke test (no model needed)
# or, if pytest is installed:
pytest tests/
```

Fixtures live in `tests/fixtures/` and exercise three unrelated domains to confirm
the schema stays domain-agnostic and that no false relations are fabricated.

---

## Design notes & deviations

- **TF-IDF salience.** `lexical_distinctiveness` = cosine distance of a chunk's
  TF-IDF vector from the corpus centroid, min-max normalised to 0..1.
  `information_density` = unique content terms / total tokens. The fitted TF-IDF
  model is reused for index sibling similarity.
- **Token counts** default to a fast offline estimate (`tokens.mode = "estimate"`).
  Set `tokens.mode = "kobold"` to use exact counts from the loaded model (adds a
  per-chunk HTTP call — not yet wired by default).
- **Index entries are per-document.** This matches the schema's literal
  Construction Logic. The schema's cross-document categorical merging example
  (one `brazilian-jiu-jitsu` entry spanning two files) is an **open question** and
  intentionally deferred — it requires clustering on top of the sibling step.
- **Robust classification.** Malformed model JSON never crashes ingest: output is
  parsed defensively, coerced against the schema enums, retried, and finally falls
  back to safe low-confidence defaults (surfaced in the run summary as
  `classify fallbacks`).

### Still open (from the schema)

Root-detection and sibling thresholds need empirical calibration; alias→embedding
concatenation strategy is configurable but unvalidated; runtime
`last_accessed`/`access_count` write-back is the orchestrator's job, not ingest's.
