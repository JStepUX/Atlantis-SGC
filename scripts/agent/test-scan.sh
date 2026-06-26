#!/usr/bin/env bash
# test-scan.sh — Analyze test coverage gaps and quality metrics (pytest conventions)
# Usage: bash scripts/agent/test-scan.sh [--scope <directory>]

source "$(dirname "$0")/_common.sh"
cd "$PROJECT_ROOT"

SCOPE="atlantis"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --scope) SCOPE="$2"; shift 2 ;;
    *) err "Unknown argument: $1"; exit 1 ;;
  esac
done

header "Test Scan — Scope: $SCOPE"

# ── Coverage Gaps ──
# Convention: atlantis/foo.py is covered if tests/ contains test_foo.py or
# foo_test.py, OR any test file references the module by name.
subheader "Coverage Gaps (source modules with no obvious test)"
missing=()
while IFS= read -r src_file; do
  base="$(basename "$src_file")"
  [[ "$base" == "__init__.py" ]] && continue
  [[ "$base" == "__main__.py" ]] && continue
  stem="${base%.py}"
  if [ -f "tests/test_${stem}.py" ] || [ -f "tests/${stem}_test.py" ]; then
    continue
  fi
  # Fallback: any test file that imports/mentions the module stem.
  if grep -rqE "\b${stem}\b" tests/ --include='*.py' $GREP_EXCLUDE 2>/dev/null; then
    continue
  fi
  missing+=("${src_file#./}")
done < <(find "$SCOPE" -name '*.py' | grep -vE "$EXCLUDE_DIRS" | sort)

if [ "${#missing[@]}" -eq 0 ]; then
  echo -e "  ${GREEN}Every source module is referenced by a test${RESET}"
else
  echo "  ${#missing[@]} module(s) with no direct/named test coverage:"
  for f in "${missing[@]}"; do echo "    - $f"; done
fi

# ── Test Metrics ──
subheader "Test Metrics"
test_files=$(find tests -name 'test_*.py' -o -name '*_test.py' 2>/dev/null | grep -vE "$EXCLUDE_DIRS" | wc -l || echo 0)
test_fns=$(grep -rE "^\s*def test_" tests/ --include='*.py' $GREP_EXCLUDE 2>/dev/null | wc -l || echo 0)
asserts=$(grep -rE "^\s*assert\b" tests/ --include='*.py' $GREP_EXCLUDE 2>/dev/null | wc -l || echo 0)
printf "  %-30s %s\n" "Test files" "${test_files:-0}"
printf "  %-30s %s\n" "test_* functions" "${test_fns:-0}"
printf "  %-30s %s\n" "assert statements" "${asserts:-0}"

# ── Mock Density ──
subheader "Mock Density"
mocks=$(grep -rE "\b(Mock|MagicMock|patch|monkeypatch|mocker)\b" tests/ --include='*.py' $GREP_EXCLUDE 2>/dev/null | wc -l || echo 0)
printf "  %-30s %s\n" "mock/patch references" "${mocks:-0}"
if [ "${test_fns:-0}" -gt 0 ]; then
  ratio=$(echo "scale=2; ${mocks:-0} / ${test_fns}" | bc 2>/dev/null || echo "n/a")
  printf "  %-30s %s per test\n" "Mock density" "$ratio"
fi

# ── Weak Assertions ──
subheader "Weak Assertions"
# `assert x` / `assert x is not None` / `assert x is None` carry little signal vs. value checks.
weak=$(grep -rnE "^\s*assert [A-Za-z_][A-Za-z0-9_.]*\s*(#|$)|is not None|is None" tests/ --include='*.py' $GREP_EXCLUDE 2>/dev/null | wc -l || echo 0)
printf "  %-30s %s\n" "Weak assertions" "${weak:-0}"
if [ "${weak:-0}" -gt 0 ]; then
  echo ""
  grep -rnE "^\s*assert [A-Za-z_][A-Za-z0-9_.]*\s*(#|$)|is not None|is None" tests/ --include='*.py' $GREP_EXCLUDE 2>/dev/null | head -15 | sed 's/^/    /'
fi

# ── Error Path Coverage ──
subheader "Error Path Coverage"
raises=$(grep -rE "pytest\.raises|with raises\(" tests/ --include='*.py' $GREP_EXCLUDE 2>/dev/null | wc -l || echo 0)
raise_stmts=$(grep -rE "^\s*raise \b" "$SCOPE" --include='*.py' $GREP_EXCLUDE 2>/dev/null | wc -l || echo 0)
printf "  %-30s %s\n" "raise statements (source)" "${raise_stmts:-0}"
printf "  %-30s %s\n" "pytest.raises (tests)" "${raises:-0}"

# ── Vague Descriptions ──
subheader "Vague Test Names"
vague=$(grep -rnE "def test_(works|it_works|basic|stuff|thing|misc)\b" tests/ --include='*.py' $GREP_EXCLUDE 2>/dev/null | wc -l || echo 0)
printf "  %-30s %s\n" "Vague test names" "${vague:-0}"
[ "${vague:-0}" -gt 0 ] && grep -rnE "def test_(works|it_works|basic|stuff|thing|misc)\b" tests/ --include='*.py' $GREP_EXCLUDE 2>/dev/null | head -10 | sed 's/^/    /'

echo ""
dim "Test scan complete"
