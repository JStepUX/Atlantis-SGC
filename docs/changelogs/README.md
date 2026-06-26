# Changelog

Monthly files, newest entries at the top. One file per month keeps any single changelog write bounded in context size — an agent updating the changelog only needs to read the current month, not the project's full history.

## Conventions

- **Filename**: `YYYY-MM.md` (e.g., `2026-04.md`). The file whose name matches `date +%Y-%m` is the one you write to today. If the current month's file doesn't exist yet, create it.
- **Empty files are not cruft.** Future-month files may be pre-seeded as empty placeholders to advertise the naming pattern and eliminate "create if missing" logic. Do not delete them.
- **New entries go at the TOP** of the current month's file, above any existing entries. Newest-first means `head` shows you the most recent activity.
- **Entry header**: `## YYYY-MM-DD — Short title`. Day-precision dates let `grep "## 2026-04-14"` find everything that shipped on a specific day without reading the file in full.
- **Entry body**: Keep-a-Changelog-style subsections (`### Added`, `### Changed`, `### Fixed`, `### Removed`, `### Security`) as needed. Only include the subsections you actually use — an entry that's only fixes doesn't need an empty `### Added`. Prose should be specific enough that a developer six months from now understands what changed and why, with file paths in backticks. No marketing tone.
- **No frontmatter.** The filename encodes the month, the entry header encodes the day, git encodes the author. Anything else is overhead.

## Querying history

These files are for posterity, not for reading end-to-end. To find something historical, `grep` across all files:

```
grep -r "<keyword>" docs/changelogs/
```

To see what shipped on a specific day:

```
grep "## 2026-04-14" docs/changelogs/2026-04.md
```

## Bootstrapping note

This directory ships empty in the boilerplate (only this README). The first changelog entry is created the first time `pre-commit-qa` runs on a real change — it creates the current month's file if it doesn't exist and adds the entry at the top. There is no pre-convention `CHANGELOG.md` archive to preserve; history starts clean with the first commit on the new codebase.
