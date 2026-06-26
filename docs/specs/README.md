# Specs

A spec is the brief an agent works from — a design or task document that drives a discrete unit of work. This is the **active** spec directory: specs live here while the work they describe is in progress.

## Lifecycle

1. A spec lands here when work on it begins (you write it, or the developer hands it to you).
2. While active, it's the source of truth for that work — read it at the start of the task it governs, not before.
3. When the work is **fully** complete, `mv` the spec to `../ignored/`. This directory and `../ignored/` are both git-ignored (specs are local working context, never committed), so it's a plain filesystem move — it just keeps this directory to only what's live. The `pre-commit-qa` gate enforces the move (item 3, "Spec Archival"): a finished spec still sitting here is a gate failure.
4. If the work is only partially done, the spec stays here — note which sections remain.

## Conventions

- One spec per unit of work. Descriptive filename (e.g. `auth-refresh-tokens.md`). No mandated frontmatter — the spec serves the work, not a schema.
- Don't read specs for unrelated work; this directory is point-of-discovery, not always-on context.

Ships empty in the boilerplate. The first spec arrives with the first spec-driven task.
