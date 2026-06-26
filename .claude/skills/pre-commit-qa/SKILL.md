---
name: pre-commit-qa
description: >
  A mandatory quality gate that enforces test coverage, localization, documentation,
  spec archival, and commit hygiene after any implementation work. Use this skill
  whenever code changes are complete and about to be committed — trigger on phrases
  like "I'm done", "ready to commit", "finished implementing", "task complete",
  "wrap up", "ship it", "PR ready", or any signal that implementation is finished
  and the work is moving toward version control. Also trigger when reviewing
  someone else's completed work before merge. This skill should fire even if the
  user doesn't explicitly ask for a quality check — if implementation just finished,
  this gate applies. Do NOT skip steps. Do NOT self-certify. Every item requires
  evidence.
---

# Pre-Commit Quality Assurance Gate

You just finished implementation work. Before anything gets committed, you must
walk through every item below and either demonstrate compliance or flag the gap.
No item is optional. No item is self-certifying — each requires you to show your
work (file paths, command output, diff snippets).

If you cannot satisfy an item, say so explicitly and explain why. Do not silently
skip items or claim compliance without evidence.

---

## 1. Test Coverage

Changes to code must have corresponding test coverage. The goal is to catch
regressions — if the code you just wrote were reverted or broken, at least one
test should fail.

**Rules:**
- Prefer real data over mocks. Mocks are acceptable only when external services
  or hardware make real data impractical (e.g., third-party APIs with rate limits,
  hardware sensors). If you reach for a mock, justify it.
- Every changed function or endpoint should have at least one test that exercises
  the new behavior.
- "Coverage" means behavioral coverage, not line-count coverage. A test that
  imports a module without asserting anything is not coverage.

**Evidence required:** List the test files you created or modified, and for each,
state what behavior it validates. If no tests were written, explain why the
changes are exempt (e.g., documentation-only changes, config-only changes).

---

## 2. Test Execution

Tests must actually run and pass. Writing tests without executing them is worse
than not writing them — it creates false confidence.

**Rules:**
- Run the full test suite, not just the new tests. Your changes may have broken
  something upstream.
- If any tests fail, fix them before proceeding. Do not commit with known
  failures unless explicitly agreed with the developer and documented in the
  commit message.

**Evidence required:** Paste or summarize the test runner output showing all
tests passing (or document agreed-upon exceptions).

---

## 3. Spec Archival (if applicable)

If this work was driven by a spec document (specs live in `docs/specs/` while
active — see `docs/specs/README.md`), the spec must be moved to `docs/ignored/`
after completion. This keeps `docs/specs/` clean for future work sessions and
preserves the spec as a local historical artifact. (Both directories are
git-ignored — see the rule below.)

**Rules:**
- Only move the spec if the work described in it is fully complete — not
  partially done.
- Use a plain `mv`. `docs/specs/` and `docs/ignored/` are git-ignored — specs
  are local working context, never committed — so there's no git history to
  preserve; just don't lose the file.
- If the spec was only partially completed, leave it in place and note which
  sections remain.

**Evidence required:** State the spec filename and confirm it was moved, or
confirm that no spec was driving this work.

---

## 4. Documentation Updates

The following project documents must be reviewed for necessary updates based on
the work just completed. "Reviewed" means you actually opened the file and
checked whether your changes require an update — not that you assumed they don't.

| Document | Path | Update when... |
|---|---|---|
| Changelog | `docs/changelogs/YYYY-MM.md` (current month) | Any user-facing or developer-facing change (always) |
| README | `README.md` | Setup steps, dependencies, project structure, or env vars changed |
| Agent Guide | `CLAUDE.md` | Project structure, conventions, or agent workflow changed |
| Agent Scripts | `scripts/agent/` | Files moved/renamed, module patterns changed, or grep targets changed |

**Rules:**
- The changelog should always be updated. Every committed change is a changelog
  entry. See `docs/changelogs/README.md` for the current convention.
- For agent utility scripts, "reviewed" means executed — not eyeballed. Run each
  script that could be affected by your changes and confirm it produces non-empty,
  plausible output. A script that silently returns nothing is worse than a missing
  script.
- For the others, if no update is needed, state why (e.g., "No new env vars or
  setup steps, README unchanged").
- Do not add boilerplate entries. Changelog entries should be specific enough that
  a developer reading them six months from now understands what changed.

**Evidence required:** For each document, state whether it was updated or why it
was skipped.

---

## 5. Commit Hygiene

Work must be broken into logical, well-written, digestible commits. One giant
commit with "implemented feature X" is not acceptable.

**Rules:**
- Each commit should represent one logical unit of change. A good heuristic: if
  you'd struggle to write a clear, specific commit message, the commit is
  probably too broad.
- Commit messages should reference the relevant spec or ticket when one exists.
- Refactors, new features, tests, and documentation updates should generally be
  separate commits (unless they're so tightly coupled that separating them would
  make either commit non-functional).
- A commit should not touch more than ~15 files unless it's a rename, refactor,
  or migration. If it does, consider splitting it.

**Git command hygiene:** When executing commits, use bare `git` commands (no
`cd` prefix). The working directory is already correct and `Bash(git:*)` is
pre-approved in settings — prefixing with `cd` breaks pattern matching and
forces unnecessary approval prompts.

**Evidence required:** List the planned commits with their messages before
executing them. The developer should approve the commit plan.

---

## 6. Git Tracking

Before committing, verify the actual state of the working tree. Do not rely on
memory of what you changed — use git commands to confirm.

**Rules:**
- Run `git status` and `git diff --stat` to enumerate all modified, added, and
  deleted files. Compare this list against your mental model of what changed. If
  there are unexpected files, investigate before committing.
- Run `git diff` (or `git diff <file>`) on any file you're unsure about to
  verify the change is intentional and complete.
- Check for untracked files that should be staged (new source files, new test
  files) and files that should NOT be staged (`.env`, credentials, build
  artifacts, editor temp files).
- Confirm no partial changes are left unstaged. If a file has both staged and
  unstaged changes, either stage the rest or stash it — mixed state leads to
  broken commits.
- Run `git log --oneline -3` to confirm you're building on the expected base
  commit and branch.

**Evidence required:** Paste or summarize the `git status` output. Flag any
surprises (unexpected files, missing files, files you expected to change but
didn't).

---

## 7. Visual Verification (UI changes only)

If the work includes UI changes (components, styles, layouts, user flows),
visual verification is required. Automated tests catch logic; they do not
catch layout shift, color rendering, responsive behavior, or interaction feel.

**Rules:**
- If a browser MCP is available (e.g., Playwright MCP at `mcp__playwright__*`),
  drive the affected routes and capture screenshots. Confirm the change
  visually before declaring the work done. Exercise the changed flow, not
  just "the page loads."
- **Logging in.** If the app gates the UI behind auth, you need a session
  before you can drive it. Use the project's documented dev-login procedure
  (a seed script, a fixture account, a magic-link bypass — whatever the
  project provides; check `README.md` / `package.json` scripts). Open the dev
  client URL the project serves on, not the API port. Do not ask the user to
  log you in — establish the session yourself. If the project has no such
  procedure yet, that gap is worth noting.
- If no browser MCP is available, run the dev server, state explicitly in the
  completion report that you could not visually verify, and ask the user to
  eyeball it. Do not claim the UI works from code inspection alone.
- This item is N/A only when the change touches zero user-visible surfaces
  (e.g., server-only refactor, test-only change, docs-only change).

**Evidence required:** Either (a) screenshots + a short description of what
was verified, or (b) an explicit disclosure that visual verification was
skipped, with the reason (no browser MCP, user elected to eyeball, etc.).

---

## Output Format

After walking through all seven items, produce a summary table:

```
| # | Check                | Status | Notes                          |
|---|----------------------|--------|--------------------------------|
| 1 | Test Coverage        | ✅ / ❌ | [brief note]                  |
| 2 | Tests Executed       | ✅ / ❌ | [brief note]                  |
| 3 | Spec Archived        | ✅ / ⬜ | [⬜ = N/A, no spec]           |
| 4 | Docs Updated         | ✅ / ❌ | [which docs touched]          |
| 5 | Commit Plan Approved | ✅ / ❌ | [number of planned commits]   |
| 6 | Git Tracking         | ✅ / ❌ | [unexpected files? clean tree?]|
| 7 | Visual Verification  | ✅ / ⬜ / ⚠️ | [⬜ = no UI; ⚠️ = UI changed but not verified; ✅ = verified] |
```

If any item is ❌, do not proceed to commit. Resolve the gap first.

---

## Final Step: Write the Approval Marker

If — and only if — every item above is ✅ (or a non-blocking ⬜ N/A), write the
approval marker. This unlocks `git commit`: the PreToolUse hook at
`.claude/hooks/pre-commit-gate.mjs` blocks every commit until this marker exists,
matches the current branch, and is < 10 minutes old. The marker is **time-
bounded, not single-use** — one QA pass covers every commit in the planned
batch (a 4-commit fix series, a refactor split into commits, etc.) as long as
they all land within the 10-minute window. Switch branches, let the marker
expire, or come back later for a new batch and you'll need to re-run this
skill — that's by design.

Do NOT write this marker if any item is ❌. Do NOT write it speculatively before
walking the list. The marker is the artifact of the QA pass, not a way around it.

```bash
mkdir -p .claude/state
node -e "
  const { execSync } = require('node:child_process');
  const fs = require('node:fs');
  fs.writeFileSync('.claude/state/pre-commit-qa-passed.json', JSON.stringify({
    branch: execSync('git rev-parse --abbrev-ref HEAD', { encoding: 'utf8' }).trim(),
    headSha: execSync('git rev-parse HEAD', { encoding: 'utf8' }).trim(),
    timestamp: new Date().toISOString(),
  }, null, 2));
"
```

After writing, proceed with the planned commits. If you cross the 10-minute
window mid-batch, the gate will block the next commit with a "stale" message —
re-run /pre-commit-qa, then continue.

