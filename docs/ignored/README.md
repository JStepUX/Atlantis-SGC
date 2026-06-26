# Ignored — Local Spec Archive

Where completed specs go to rest. When the work a spec drove is finished, `pre-commit-qa` (item 3, "Spec Archival") has you move the spec here so `../specs/` only ever holds what's live.

**This directory is git-ignored and never committed.** It — and `../specs/` — are local working context, not project history; there's no value in shipping legacy specs to the remote. Only this README is tracked, so the convention travels with the repo even though the specs never do.

## Using it

- During normal work you don't read from here — it's a local graveyard, not live context. That's the point: it keeps `../specs/` and the active surface lean.
- If you need the rationale behind a past decision, `grep` your local copy of this directory. Don't expect it to exist on a fresh clone — by design, it won't.

Ships empty in the boilerplate.
