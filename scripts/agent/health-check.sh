#!/usr/bin/env bash
# health-check.sh — byte-compile + ruff/mypy (if present) + tests + git + markers
# Usage: bash scripts/agent/health-check.sh

source "$(dirname "$0")/_common.sh"
cd "$PROJECT_ROOT"

header "Health Check"

# ── Byte-compile (cheap syntax check across the package) ──
subheader "Byte-compile (compileall atlantis)"
set +e
cc_output=$("$PY" -m compileall -q atlantis 2>&1)
cc_exit=$?
set -e
[ -n "$cc_output" ] && echo "$cc_output" | tail -20
if [ "$cc_exit" = 0 ]; then echo -e "  ${GREEN}✓ Passed${RESET}"; else echo -e "  ${RED}✗ Failed (exit $cc_exit)${RESET}"; fi
echo ""

# ── Lint (ruff) — optional ──
subheader "Lint — ruff (if installed)"
if "$PY" -m ruff --version >/dev/null 2>&1; then
  set +e; "$PY" -m ruff check atlantis 2>&1 | tail -30; set -e
else
  dim "  (ruff not installed — skipped)"
fi
echo ""

# ── Types (mypy) — optional ──
subheader "Types — mypy (if installed)"
if "$PY" -m mypy --version >/dev/null 2>&1; then
  set +e; "$PY" -m mypy atlantis 2>&1 | tail -20; set -e
else
  dim "  (mypy not installed — skipped)"
fi
echo ""

# ── Tests ──
subheader "Tests"
set +e
if "$PY" -m pytest --version >/dev/null 2>&1 && [ -d tests ]; then
  "$PY" -m pytest -q 2>&1 | tail -30
  t_exit=${PIPESTATUS[0]}
elif [ -f tests/test_pipeline.py ]; then
  "$PY" tests/test_pipeline.py 2>&1 | grep -v "onnx.tar.gz\|MiniLM" | tail -20
  t_exit=${PIPESTATUS[0]}
else
  dim "  (no tests found)"
  t_exit=0
fi
set -e
if [ "${t_exit:-1}" = 0 ]; then echo -e "  ${GREEN}✓ Passed${RESET}"; else echo -e "  ${RED}✗ Failed (exit ${t_exit})${RESET}"; fi
echo ""

# ── Git Status ──
subheader "Git Status"
git status --short 2>/dev/null || dim "  (not a git repo)"

# ── Code Markers ──
subheader "Code Markers"
for marker in TODO FIXME HACK XXX; do
  count=$(grep -rE "\b${marker}\b" . --include='*.py' $GREP_EXCLUDE 2>/dev/null | wc -l || true)
  printf "  %-8s %d\n" "$marker" "${count:-0}"
done

echo ""
dim "Health check complete"
