The role of this file is to describe common mistakes and confusion points that agents might encounter as they work in this project. If you ever encounter something in the project that surprises you, please alert the developer working with you and indicate that this is the case in this file to help prevent future agents from having the same issue.

## How to add entries

Each entry documents a real gotcha encountered during a session. The format:

```
## <Short, scannable title> (<source task or context>, <date>)

<Two to four sentences describing the surprise, why it happens, and what the
correct behavior looks like. Point at the relevant file paths so the next
agent can verify.>
```

Keep entries tight. If a section would be longer than a screenful, it probably
belongs in a dedicated doc under `docs/` or as a comment at the source. This
file is for **confusion pointers**, not long-form documentation.

Before adding an entry, ask whether the surprise can be invalidated instead
of documented:

- **Push to source.** A pattern with a clear home (a function, a hook, a
  middleware) belongs in JSDoc or a comment at that site. Agents reading the
  code find it when they need it.
- **Build a structural check.** Diligence traps ("remember to update X when
  you change Y") should become tests, derived assertions, or refactors that
  remove the duplication. Core Value #3.
- **Write the entry only when neither works** — when the surprise is
  cross-cutting, environmental, or a one-shot heads-up that has no natural
  home in the codebase.

## `related_chunks` is empty by design for a thematically diverse corpus (first ingest run, 2026-06-27)

Seeing `related_chunks: []` on every chunk after an ingest looks like the relate
stage is broken, but it usually isn't. `_compute_related` in `atlantis/pipeline.py`
only links chunks **across different documents** (it skips same-`document_slug`
pairs) and requires an **exact topic-string Jaccard ≥ `related_min_overlap`**
(default 0.20, `config.py` `SalienceConfig`). Because the classifier coins
specific, per-chunk topic strings, two documents on unrelated subjects share zero
exact topic strings, so the intersection is empty and the threshold never even
applies. This is expected: relations populate only when documents genuinely share
topic vocabulary. Confirm before "fixing" by diffing topic sets across documents
(empty cross-document intersection ⇒ empty `related_chunks` is correct).
## The PATH `python` is not the project interpreter (brain-pack export, 2026-07-04)

On this machine `python` on PATH resolves to an unrelated agent venv
(3.11, no numpy/chromadb), so `python tests/test_pipeline.py` fails at import.
The interpreter with this project's dependencies is
`C:\Users\virtu\AppData\Local\Python\pythoncore-3.14-64\python.exe` (matches
"developed on 3.14" in CLAUDE.md). Use it explicitly for `-m atlantis` and the
tests; `py -0` lists nothing useful here.
