# Atlantis — Brain-Pack Compiler for SGC

Atlantis compiles raw documents into **`sgc-brain/1` knowledge packs** — the
mountable "brains" consumed by the sibling
[SGC (Salience-Gated Cognition)](../sgc) repo. Documents are chunked, annotated
with frontmatter per the
**[Atlantis Salience Schema v1.0](atlantis-salience-schema-v1.md)**, and
exported as a single JSON pack per brain. **Only lexical fields cross the
contract** — chunk text, summaries, topics, and hand-editable *aliases* (the
synonym bridge SGC's deterministic TF-IDF retrieval leans on). No embeddings,
no vectors, no model at SGC's runtime.

The structure is domain-agnostic: BJJ techniques, Minnesota trivia, Star Wars
lore, and couscous recipes all flow through the same fields — the domain lives in
the *values*, never the *field names*.

> **The Chroma tail is dormant, not gone.** Atlantis originally terminated in a
> Chroma vector DB. That machinery (TF-IDF salience → categorical index →
> Chroma/MiniLM embeddings) is retained behind `ingest --full` as Phase 2b
> infrastructure — the future embeddings-vs-lexical retrieval comparison — but
> it is **not** part of the pack contract and the default ingest never runs it.

---

## Pipeline at a glance

```
                       ┌──────────────── the compile path (default) ───────────────┐
Data/raw/*.md ──▶ chunk ──▶ classify (Gemma or --stub) ──▶ assemble + validate
                                                                  │
      SGC ◀── import ◀── pack.json ◀── export ◀── Data/chunks/*.md (hand-editable)
                                                                  +
                                            Data/index.json (backend stamp → stub provenance)

  --full only (dormant Phase 2b tail): TF-IDF salience ──▶ relate ──▶ index ──▶ Chroma DB
```

| Stage | Module | What it produces | Runs |
|---|---|---|---|
| Discover + chunk | `chunking.py` | identity, navigation, heading-aware bodies, token counts | always |
| Classify | `classify.py` | `summary`, `topics`, `aliases` (pack fields) + `chunk_type`, `goal_affinity`, `utility`, `authority`, `confidence`, `standalone` | always |
| Assemble | `schema.py` | ordered frontmatter, `topic_path`, `specificity`, validation | always |
| Export | `export.py` | the `sgc-brain/1` pack (active chunks, lexical fields, stub provenance) | on `export` |
| Salience | `salience.py` | `lexical_distinctiveness`, `information_density` (corpus TF-IDF) | `--full` |
| Relate | `pipeline.py` | `related_chunks` (cross-doc topic overlap) | `--full` |
| Index | `index_builder.py` | root terms, entries, sibling similarity, `index_ref` | `--full` |
| Persist | `chroma_writer.py` | flattened Chroma metadata + alias-augmented embeddings | `--full` |

### What is computed vs. generated

- **Atlantis (deterministic):** identity, navigation, `topic_path`, `specificity`,
  timestamps, token counts, the pack export itself (+ TF-IDF salience and
  related/index links under `--full`).
- **Small model (Gemma via KoboldCPP, optional):** the subjective fields —
  `summary`, `topics`+depths, `aliases`, `chunk_type`, `goal_affinity`,
  `utility`, `authority`, `confidence`, `standalone`. With `--stub` these come
  from deterministic fallbacks instead (first-sentence summaries, frequency
  topics, empty aliases) and the pack honestly reports `stub: true`.

---

## Setup

```bash
pip install -r requirements.txt
```

Requires **Python 3.11+** (tested on 3.14). The compile path needs only
**PyYAML** from that list; `chromadb` (+ its ~80 MB MiniLM ONNX download on
first use) and `numpy` are pulled in **only** by `ingest --full`, and
`requests` only by non-stub classification.

Non-stub classification talks to a local **KoboldCPP** server over its
OpenAI-compatible API. Defaults assume `http://localhost:5001/v1` — change in
`config/atlantis.toml` if needed. The whole compile path runs **without** any
model using `--stub`.

---

## Usage — compiling a brain

```bash
# 1. Drop documents into Data/raw/ (.md, .markdown, .txt — subdirs scanned recursively)

# 2. Check pack-readiness and environment
python -m atlantis doctor

# 3. Ingest: raw docs -> annotated chunk files (the compile path)
python -m atlantis ingest              # with KoboldCPP enrichment (richer topics/aliases)
python -m atlantis ingest --stub       # fully offline, no model; pack reports stub: true

# 4. (Optional, recommended) Hand-edit Data/chunks/*.md frontmatter —
#    especially `aliases:`, the synonym bridge for SGC's lexical retrieval.
#    NOTE: re-running ingest REGENERATES chunk files and destroys hand edits.
#    Edit AFTER your final ingest; re-ingest only when the source docs change.

# 5. Export the pack (filename stem = default pack id). --archive then retires
#    the corpus: raw docs + chunk files + index.json move to
#    Data/archive/<pack-id>_<stamp>/ with a copy of the pack, leaving the
#    working dirs clean for the next brain — so stale chunks can never bleed
#    into the next pack. (Runs only after a successful export; omit the flag
#    while you still want to re-export the same corpus.)
python -m atlantis export --out my-brain.json --name "My Brain" --description "..." --archive

# 6. Import my-brain.json in SGC ("Begin again" -> Mount brains -> Import pack…)
#    Re-exporting with the same id overwrites on import — the edit/re-export loop.

# Iteration helpers
python -m atlantis ingest --limit 5    # only the first N chunks
python -m atlantis ingest --plain      # plain log instead of the live dashboard

# Dormant Phase 2b tail (not needed for packs)
python -m atlantis ingest --full       # + salience, index, Chroma/MiniLM
python -m atlantis query "grip" -n 5   # probe the Chroma collection (--full builds only)
```

### Watching it run

On an interactive terminal, `ingest` shows a live dashboard. The slow stage is
**Classify** (one model call per chunk, run sequentially; instant under
`--stub`), so it gets a progress bar with a live ETA. In the default compile
mode the Phase 2b rows report `done skipped (compile mode; --full restores)`.
The dashboard auto-falls back to a plain log when output is piped/redirected or
the terminal isn't a TTY; force it with `--plain`. The event layer
(`atlantis/reporting.py`) is UI-agnostic.

### Outputs

| Path | What | Mode |
|---|---|---|
| `Data/chunks/<chunk_id>.md` | Human-inspectable, hand-editable chunk = frontmatter + body — **the export source** | always |
| `Data/index.json` | Carries the `backend` stamp export reads for `stub` provenance (plus the categorical index under `--full`) | always |
| `<pack>.json` (via `export`) | The `sgc-brain/1` knowledge pack SGC imports | on `export` |
| `Data/chroma/` | Persistent Chroma DB (Phase 2b) | `--full` |
| `Data/index.md` | Human-readable index | `--full` |

---

## Configuration

All knobs live in [`config/atlantis.toml`](config/atlantis.toml). Highlights:

- `[chunking]` — `target_tokens` / `max_tokens` / `min_tokens` and heading-respect.
- `[model]` — KoboldCPP `base_url`, `model`, temperature, timeout, retries
  (non-stub enrichment only).
- `[provenance]` / `[temporal]` — defaults for `source_type`, `decay_class`, etc.
- `[embeddings]` / `[index]` / `[salience]` — Phase 2b tail only (`--full`).

Override the config path for any command: `--config path/to/other.toml`.

---

## Testing

```bash
python tests/test_pipeline.py     # compile mode + --full mode smoke (no model needed)
python tests/test_export.py       # pack contract: mapping, provenance, determinism
# or, if pytest is installed:
pytest tests/
```

Fixtures live in `tests/fixtures/` and exercise three unrelated domains to confirm
the schema stays domain-agnostic. (The same fixtures, stub-ingested with
hand-authored aliases, are the committed `brain-fixture.json` in SGC's eval
suite — the two repos test the contract from both ends.)

---

## Design notes & deviations

- **Aliases are the load-bearing enrichment.** SGC retrieves lexically
  (TF-IDF cosine over stems); an alias is the only way a pack can match
  vocabulary its text never uses. Gemma proposes aliases at classify time;
  stub mode leaves them empty for hand-authoring. Either way they are plain
  frontmatter — audit and edit them before export.
- **Stub provenance is read from disk, not trusted from a flag.** Ingest stamps
  the classifier backend into `index.json`; export derives `source.stub` from
  it. A missing stamp degrades conservatively to `stub: false`.
- **Robust classification.** Malformed model JSON never crashes ingest: output is
  parsed defensively, coerced against the schema enums, retried, and finally falls
  back to safe low-confidence defaults (surfaced in the run summary as
  `classify fallbacks`).
- **Token counts** default to a fast offline estimate (`tokens.mode = "estimate"`).
  Set `tokens.mode = "kobold"` for exact counts from the loaded model (adds a
  per-chunk HTTP call — not yet wired by default).
- **Phase 2b tail (dormant, `--full`):** TF-IDF salience (`lexical_distinctiveness`
  = cosine distance from the corpus centroid; `information_density` = unique
  content terms / total tokens), per-document index entries, and alias-augmented
  MiniLM embeddings in Chroma. Retained for a future embeddings-vs-lexical
  retrieval comparison against SGC's brain-eval baseline; none of it reaches a
  pack today (`sgc-brain/2` may adopt the salience fields — schema bump required).
