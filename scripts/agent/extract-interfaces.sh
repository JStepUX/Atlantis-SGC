#!/usr/bin/env bash
# extract-interfaces.sh — Extract public signatures from a module or directory
# Usage: bash scripts/agent/extract-interfaces.sh <file-or-directory>
# Shows: top-level functions, classes (+ method signatures), module constants.
# Skips bodies. Used by test-adversary for context gathering.

source "$(dirname "$0")/_common.sh"
cd "$PROJECT_ROOT"

if [ $# -lt 1 ]; then
  err "Usage: extract-interfaces.sh <file-or-directory>"
  exit 1
fi

TARGET="$1"
if [ ! -e "$TARGET" ]; then
  if [ -e "$PROJECT_ROOT/$TARGET" ]; then
    TARGET="$PROJECT_ROOT/$TARGET"
  else
    err "Path not found: $TARGET"
    exit 1
  fi
fi
TARGET="$(cd "$(dirname "$TARGET")" && pwd)/$(basename "$TARGET")"

process_file() {
  local file="$1"
  local rel="${file#$PROJECT_ROOT/}"
  sigs=$(extract_signatures "$file")
  if [ -n "$sigs" ]; then
    subheader "$rel"
    echo "$sigs"
  else
    dim "  $rel — no public signatures"
  fi
}

if [ -f "$TARGET" ]; then
  header "Interfaces: $(basename "$TARGET")"
  process_file "$TARGET"
elif [ -d "$TARGET" ]; then
  rel_dir="${TARGET#$PROJECT_ROOT/}"
  header "Interfaces: $rel_dir"
  py_files=$(find "$TARGET" -name '*.py' | grep -vE "$EXCLUDE_DIRS" | sort)
  if [ -z "$py_files" ]; then
    dim "  No .py files found in $rel_dir"
    exit 0
  fi
  echo "Processing $(echo "$py_files" | wc -l) file(s) in $rel_dir"
  while IFS= read -r file; do
    process_file "$file"
  done <<< "$py_files"
else
  err "Not a file or directory: $TARGET"
  exit 1
fi

echo ""
dim "Extraction complete"
