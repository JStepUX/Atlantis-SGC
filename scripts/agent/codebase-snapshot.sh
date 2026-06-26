#!/usr/bin/env bash
# codebase-snapshot.sh — Project orientation in one call (tree, counts, git, entrypoints)
# Usage: bash scripts/agent/codebase-snapshot.sh

source "$(dirname "$0")/_common.sh"
cd "$PROJECT_ROOT"

header "Project Structure"
find . -maxdepth 4 \
  -not -path '*/__pycache__/*' \
  -not -path '*/.git/*' -not -path '*/.git' \
  -not -path '*/.venv/*' -not -path '*/venv/*' \
  -not -path '*/Data/chroma/*' -not -path '*/Data/chunks/*' \
  -not -path '*/.pytest_cache/*' -not -path '*/.mypy_cache/*' \
  -not -path '*/.ruff_cache/*' -not -path '*.egg-info/*' \
  \( -type f -o -type d \) | sort | head -120

header "File Counts by Type"
echo "Python (.py):"
find . -name '*.py' | grep -vE "$EXCLUDE_DIRS" | wc -l
echo "Markdown (.md):"
find . -name '*.md' | grep -vE "$EXCLUDE_DIRS" | wc -l
echo "TOML (config):"
find . -maxdepth 2 -name '*.toml' | grep -vE "$EXCLUDE_DIRS" | wc -l

header "Recent Git History (last 15 commits)"
git log --oneline -15 2>/dev/null || dim "(not a git repo)"

header "Python Package & Dependencies"
[ -f pyproject.toml ] && echo "  ✓ pyproject.toml"
if [ -f requirements.txt ]; then
  echo "  requirements.txt:"
  grep -vE '^\s*#|^\s*$' requirements.txt | sed 's/^/    /'
fi

header "Entry Points"
if [ -f atlantis/__main__.py ]; then
  subcommands=$(grep -oE 'add_parser\("[a-z]+"' atlantis/__main__.py | sed -E 's/add_parser\("//; s/"//' | tr '\n' ' ')
  echo "  python -m atlantis  (subcommands: ${subcommands:-?})"
else
  dim "  (no atlantis/__main__.py)"
fi

header "Key Config Files"
for f in config/atlantis.toml pyproject.toml requirements.txt .env .env.example; do
  [ -f "$f" ] && echo "  ✓ $f"
done

echo ""
dim "Snapshot generated from $PROJECT_ROOT"
