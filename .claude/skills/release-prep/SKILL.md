---
name: release-prep
description: >
  Prepares a release. Reads the changelog entries that pre-commit-qa
  has accumulated since the last release marker, cross-checks against git for
  any bypassed commits, proposes a semver bump, and — on explicit user approval
  — inserts a release marker, bumps the version, commits, and tags. Does not
  push and does not deploy. Use before running the project's deploy command, or
  when the user signals release intent ("ready to deploy", "time to ship", "cut
  a release", "write the changelog", "release prep"). The authoring side of the
  release pipeline — complements `pre-commit-qa` (which gates individual commits)
  by gating the batch that becomes a release.
---

# Release Preparation Skill

## Trust model — read before doing anything

**`pre-commit-qa` is load-bearing for this skill.** Every commit should have
already added a `## YYYY-MM-DD` entry to the current month's changelog file as
part of the `pre-commit-qa` gate. That means by release time, the changelog
already contains high-quality, in-context entries for every commit since the
last release. Your job is to *assemble and ceremony*, not to infer content
from `git log`.

You will cross-check against git to catch any commit that bypassed the gate,
but git is a **sanity check, not a source.** If the changelog and git
disagree, you flag the gap and ask the user — you do not paper over it by
fabricating prose from commit subjects.

**The release boundary is a marker line inside the changelog file**, in this
format:

```
<!-- release: vX.Y.Z @ YYYY-MM-DD sha=<7-char commit> -->
```

It's an HTML comment, invisible in rendered Markdown, parseable by this
skill. Entries above the top-most marker (in the current month file, walking
back through prior months if needed) are "unreleased." On release, you insert
a new marker above the entries you just released.

---

## 1. Verify the repo is in a releasable state

- **Clean working tree.** Run `git status`. Uncommitted changes → stop, tell
  the user, offer to run `pre-commit-qa` on the pending work first.
- **Expected branch.** Confirm `git branch --show-current` is `main` (or the
  branch the user named). Feature branch → confirm intent.
- **Up to date with origin.** `git fetch && git rev-list --count HEAD..origin/main`
  should be zero.

Summarize `git status` + the ahead/behind in your report.

---

## 2. Find the last release marker (or detect first-run)

Scan the changelog for the most recent marker:

1. Start with `docs/changelogs/YYYY-MM.md` for the current month.
2. Read top-to-bottom. The first `<!-- release: ... -->` line you find is
   the most recent marker.
3. If not found, walk back through prior monthly files in reverse chronological
   order until you find one, or run out of files.

**If no marker exists anywhere** (first-run / bootstrap case for a new
codebase): switch to §3. Otherwise, record:
- Marker version (e.g., `v0.2.0`)
- Marker date
- Marker SHA
- The file and line where it was found

Entries **above** the marker (across however many files) are the unreleased set.

---

## 3. First-run bootstrap flow

**If and only if no marker exists anywhere in `docs/changelogs/`:**

Tell the user this is the first formal release for the project. Report:
- Current `__version__` in `atlantis/__init__.py` (probably `1.0.0`).
- Count of existing entries across all changelog files.
- Date of the earliest existing entry.

Propose one of two starting modes and ask the user to pick:

- **Retroactive baseline:** Treat the current HEAD commit as the boundary
  for a baseline release matching the current `atlantis/__init__.py` version. All
  existing changelog entries become "pre-baseline history." Inserts a marker
  at the top of the current-month file, tags the current HEAD, and
  **does not bump the version** — this run is just establishing the baseline.
  Next run does the real first release.
- **Cut now:** Everything in the changelog is a new first release. Propose
  a version the user wants (the current `__version__` if unset, or whatever
  they name). Normal semver proposal doesn't apply since there's no prior
  baseline to compare against.

Default recommendation: **retroactive baseline**. It establishes the convention
without conflating "baselining the history" with "shipping new work." The next
run of the skill then handles the real first release cleanly.

Whichever the user picks, get explicit approval before doing anything.

---

## 4. Collect unreleased entries

Read the changelog entries above the last marker (or all entries, in first-run
cut-now mode). For each entry, extract:

- Date header (`## YYYY-MM-DD — Title`)
- Subsections present (`### Added`, `### Changed`, `### Fixed`, `### Removed`,
  `### Security`)
- Bullet count per subsection

You don't need to re-read the prose — `pre-commit-qa` wrote it, and the
human will review the full assembled entry before shipping.

---

## 5. Cross-check against git (sanity pass)

Run `git log --oneline <marker-sha>..HEAD` (or `git log --oneline` for
first-run cut-now mode, though scope limits may apply).

Compare:
- Commits with dates in the unreleased window vs.
- Changelog day-entries covering the same dates.

**Flag any of these as needing user attention:**
- Commits on a day with no corresponding changelog entry.
- Commits whose subject suggests user-visible change but no matching entry.
  (Heuristic: `feat:`, `fix:`, `security:` prefixes, or anything touching
  `atlantis/`, `config/`, `scripts/`.)
- Merge commits or squash-merges where the original commits may have been
  documented but the merge commit creates ambiguity about ordering.

Do NOT write changelog content for bypassed commits yourself. Report the gaps
and ask the user to either add entries (which triggers `pre-commit-qa`
manually) or confirm the commits are intentionally undocumented (e.g.,
dependency bumps, pure-refactor commits).

If the cross-check comes up clean, state that plainly.

---

## 6. Propose the semver bump

Based on the subsection composition of the unreleased entries, following
conventional semver:

- Any `### Removed` that represents a breaking public API change → **major.**
  Stop and get explicit confirmation from the user before proceeding. Major
  bumps are nearly always a deliberate decision, not an accident.
- Any `### Added` → **minor.**
- Only `### Fixed` / `### Security` / internal `### Changed` → **patch.**

State clearly: "Current `0.1.0` → proposed `0.2.0` (minor, driven by Added
entries in 2026-04-23 and 2026-04-25)."

Do not touch `atlantis/__init__.py` until the user confirms.

---

## 7. Present the staged release for review

Produce a summary (format in §9) that lets the user see the shape at a glance.
Do not commit, tag, or edit files yet. The user:

- Reviews the proposed version.
- Reviews the list of entries included.
- Reviews any cross-check flags.
- Edits any changelog entries in-place if they want to polish before ship.
- Replies with `approve` or requests changes.

If they request changes, iterate. Nothing gets persisted to a commit until
explicit approval.

---

## 8. After explicit approval

Execute in this order:

1. **Insert the new marker** at the top of the current-month changelog file,
   above all unreleased entries. Format:
   ```
   <!-- release: vX.Y.Z @ YYYY-MM-DD sha=<will-be-filled-post-commit> -->
   ```
   The SHA placeholder gets resolved after the commit exists.

2. **Bump `atlantis/__init__.py`** `__version__` to the approved value.

3. `git add docs/changelogs/<current-month>.md atlantis/__init__.py` (and any other
   changelog files if entries spanned months).

4. `git commit -m "chore(release): vX.Y.Z"` with a body listing the included
   entries by date header, or a short summary if the list is long.
   Use the heredoc pattern from CLAUDE.md's commit-message guidance.

5. **Resolve the SHA placeholder.** Get the commit's 7-char SHA via
   `git rev-parse --short HEAD`, then `Edit` the changelog file to replace
   `sha=<will-be-filled-post-commit>` with the real SHA. Amend the commit
   with the fix: `git add <file> && git commit --amend --no-edit`.

   (Amend is acceptable here — the commit hasn't been pushed and the amend
   is a mechanical fixup for a placeholder we couldn't resolve before the
   commit existed. This is the one exception to CLAUDE.md's "prefer new
   commit over amend" guidance; flag it in your report so the user sees it.)

6. `git tag vX.Y.Z` (lightweight) — unless the user asked for annotated,
   in which case `git tag -a vX.Y.Z -m "Release vX.Y.Z"`.

7. Tell the user the release is committed and tagged locally. Remind them to
   `git push && git push --tags` before running the project's deploy command.
   **Do not push and do not deploy** — those are confirmation-worthy actions,
   and the scope of approval for this skill was the changelog + bump + tag,
   not the push.

If the user rejects the draft at step 7, loop back. Nothing persists.

---

## 9. Output format

After §7, produce a summary that looks like this:

```
Release Prep Summary
─────────────────────

Last marker:        v0.2.0 @ 2026-04-20 (sha 697601e, in 2026-04.md:45)
  — or —
Last marker:        none (first-run — see bootstrap options below)

Unreleased entries: 3 across 2026-04.md
  · 2026-04-23 — Max tokens bump + truncation UI   (Fixed, Changed, Added)
  · 2026-04-22 — Gitignore specs directory          (Changed)
  · 2026-04-21 — Paced SSE render buffer            (Added, Changed, Fixed)

Proposed version:   0.2.0 → 0.3.0 (minor, driven by Added entries)

Git cross-check:    ✓ clean (5 commits, 3 entries, all commits mapped)
  — or —
Git cross-check:    ⚠ 2 commits without changelog coverage
  · 4d6a503 Dependabot adjustment to prevent Supply Chain attack vulnerability
  · 697601e Style updates

Ready to proceed?   Reply `approve` to insert marker, bump package.json, commit, and tag.
                    Or request edits.
```

For first-run:

```
Release Prep — First Run (Bootstrap)
─────────────────────────────────────

No release markers found in docs/changelogs/. This is the project's first
formal release.

Current __version__:  1.0.0  (atlantis/__init__.py)
Changelog entries:    17 across 2026-04.md
Earliest entry:       2026-04-08

Pick a starting mode:

  (a) Retroactive baseline — tag current HEAD as v0.1.0, insert marker, treat
      existing entries as pre-v0.1.0 history. Next run cuts the real v0.1.1
      or v0.2.0.
  (b) Cut now — treat existing changelog as the content of a new release.
      Propose a version.

Which?
```

---

## What this skill never does

- Commits without explicit user approval.
- Pushes to remote.
- Runs the deploy command or any deploy step.
- Fabricates changelog content from commit subjects for bypassed commits.
- Bumps a major version without explicit confirmation.
- Silently ignores a missing marker — always fails loudly and explains why.
- Moves or modifies prior release markers.
