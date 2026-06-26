---
name: recon
description: >
  Discovery-phase skill for symptom-shaped tasks. Use when the user hands you
  a vague problem, a bug report, a console error, or a "this is broken" style
  request rather than a well-specified feature. Produces a grounded problem
  brief you can either act on directly or hand to the project-coordinator
  agent as a sharp, pre-diagnosed task spec. Closes the gap between "here's
  a symptom" and "here's a decomposable plan".
---

# Recon — Symptom → Grounded Problem Brief

The project-coordinator agent is designed to take well-specified tasks and
decompose them. When the inbound request is a symptom ("X is broken", "users
are seeing Y", "the console says Z"), it lacks the grounding to do its best
work. Your job in this skill is to produce that grounding cheaply, using the
bash layer rather than raw tool calls, so the handoff (or direct fix) is
sharp.

## Step 1: Baseline — what changed recently

Always start here. Run:

```bash
bash scripts/agent/git-context.sh
```

Read the output for signals: recent commits, uncommitted changes, which files
were touched last. Most production regressions trace back to a commit in the
last few. Note the suspect commits but do not assume; the symptom may be old
code newly exposed.

## Step 2: Parse the symptom

Read the user's request carefully and extract concrete signals:

- **Error strings** — exact text from console, stack traces, HTTP status codes
- **File paths or URLs** — anything the user named explicitly
- **Feature names** — what the user calls the broken thing
- **Environment** — local vs deployed, which browser, which route

Write these down as a short list. If any are missing and would materially
change your investigation, ask the user before running more scripts —
discovery is cheap but not free, and targeted is better than broad.

## Step 3: Run the right follow-up scripts

Based on what you extracted, pick from:

- **Error mentions a file path** → `bash scripts/agent/file-context.sh <path>`
  to see the file and its imports in one shot.
- **Error mentions a feature or keyword** → `bash scripts/agent/related-files.sh <term>`
  to find everything touching it.
- **Symptom involves "what depends on X"** → `bash scripts/agent/trace-imports.sh <file-or-symbol>`
- **Symptom involves DB or API routes** → `bash scripts/agent/schema-dump.sh`
- **You don't remember what's in the bash library** → invoke `/bash-tools` first.

Run scripts in parallel when they are independent. Do not run scripts you
don't need; each one burns context.

## Step 4: Produce the brief

Synthesize a short, structured brief with these sections. Keep it tight — a
brief that runs more than ~200 words is usually trying too hard.

```
## Symptom
[One sentence — what the user reported, verbatim or near-verbatim]

## Likely root cause
[One or two sentences with file path + line number if known]

## Evidence
[2–4 bullets: recent commits touching the suspect file, related code, grep
hits, anything concrete]

## Red herrings
[Anything in the error output that looks relevant but probably isn't, so the
next reader doesn't chase it]

## Recommended next step
[One of: "fix directly (trivial)", "delegate to project-coordinator with this
brief", "ask user clarifying question first". Pick one.]
```

## Step 5: Hand off or act

- If the brief says **fix directly** — proceed to the fix, no coordinator.
  Trivial one-file-one-line bugs do not need decomposition.
- If the brief says **delegate** — pass the brief verbatim to the
  project-coordinator agent as the inbound task. It now has a grounded
  problem and can jump straight to decomposition.
- If the brief says **ask user** — surface the question, do not guess.

## When NOT to use this skill

Skip this skill when the user's request is already well-specified ("add a
new settings tab that does X"), when the task is feature work rather than
bug-shaped, or when the work is obviously trivial and the recon itself would
take longer than the fix. Core value #6: let friction drive the architecture,
not speculation — don't run a recon pass out of habit.
