#!/usr/bin/env bash
# trace-imports.sh — Find files that import a given module/symbol (2 levels deep)
# Usage: bash scripts/agent/trace-imports.sh <file-path-or-symbol>

source "$(dirname "$0")/_common.sh"
cd "$PROJECT_ROOT"

if [ $# -lt 1 ]; then
  err "Usage: trace-imports.sh <file-path-or-symbol>"
  exit 1
fi

TARGET="$1"

# File path (atlantis/config.py) → derive the module stem ('config').
# Bare name (load_config) → treat as a symbol and search directly.
if [[ "$TARGET" == *.py || "$TARGET" == */* ]]; then
  CLEAN="${TARGET%.py}"
  STEM="$(basename "$CLEAN")"
  KIND="module"
else
  STEM="$TARGET"
  KIND="symbol"
fi

header "Import Trace: \"$TARGET\" ($KIND)"

# Match Python imports referencing the stem: `import x.STEM`, `from x import STEM`,
# `from .STEM import ...`, `from x.STEM import ...`.
subheader "Level 1 — Direct importers"
l1_files=$(grep -rlE "^(import|from)\b.*\b${STEM}\b" . \
  --include='*.py' $GREP_EXCLUDE 2>/dev/null \
  | grep -v "${TARGET#./}" || true)

if [ -z "$l1_files" ]; then
  dim "  No files import \"$STEM\""
  exit 0
fi

l1_count=$(echo "$l1_files" | wc -l)
echo "  $l1_count file(s) reference \"$STEM\":"
echo ""

while IFS= read -r file; do
  rel="${file#./}"
  match=$(grep -m 1 -E "^(import|from)\b.*\b${STEM}\b" "$file" 2>/dev/null || true)
  echo -e "  ${GREEN}+-- $rel${RESET}"
  [ -n "$match" ] && echo "  |   $(echo "$match" | sed 's/^[[:space:]]*//')"

  # Level 2: who imports this L1 file's module?
  l1_stem="$(basename "${file%.py}")"
  l2_files=$(grep -rlE "^(import|from)\b.*\b${l1_stem}\b" . \
    --include='*.py' $GREP_EXCLUDE 2>/dev/null | grep -v "^${file}$" | grep -v "^${file#./}$" || true)

  if [ -n "$l2_files" ]; then
    l2_count=$(echo "$l2_files" | wc -l)
    echo "  |   (imported by $l2_count file(s)):"
    echo "$l2_files" | head -5 | while IFS= read -r l2; do
      echo "  |     +-- ${l2#./}"
    done
    [ "$l2_count" -gt 5 ] && dim "  |     ... and $((l2_count - 5)) more"
  else
    dim "  |   (no further importers)"
  fi
  echo ""
done <<< "$l1_files"

dim "Trace complete (2 levels deep)"
