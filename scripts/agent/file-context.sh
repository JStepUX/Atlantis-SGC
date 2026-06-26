#!/usr/bin/env bash
# file-context.sh — File + imported signatures (the centerpiece utility)
# Usage: bash scripts/agent/file-context.sh <file-path> [--no-imports]
# Shows the file content, extracts imports, resolves them, and shows exported signatures.

source "$(dirname "$0")/_common.sh"
cd "$PROJECT_ROOT"

# ── Main ──

if [ $# -lt 1 ]; then
  err "Usage: file-context.sh <file-path> [--no-imports]"
  exit 1
fi

TARGET="$1"
SHOW_IMPORTS=true
[ "${2:-}" = "--no-imports" ] && SHOW_IMPORTS=false

# Resolve relative to project root
if [ ! -f "$TARGET" ]; then
  if [ -f "$PROJECT_ROOT/$TARGET" ]; then
    TARGET="$PROJECT_ROOT/$TARGET"
  else
    err "File not found: $TARGET"
    exit 1
  fi
fi

TARGET="$(cd "$(dirname "$TARGET")" && pwd)/$(basename "$TARGET")"
REL_PATH="${TARGET#$PROJECT_ROOT/}"

header "File: $REL_PATH"
line_count=$(wc -l < "$TARGET")
echo "Lines: $line_count"

# Show file content (cap at 300 lines)
subheader "Content"
if [ "$line_count" -le 300 ]; then
  cat -n "$TARGET"
else
  head -n 300 "$TARGET" | cat -n
  dim "  ... (truncated, showing 300 of $line_count lines)"
fi

if [ "$SHOW_IMPORTS" = false ]; then
  exit 0
fi

# ── Extract and resolve imports ──
header "Import Analysis"
import_paths=$(extract_imports "$TARGET")

if [ -z "$import_paths" ]; then
  dim "  No imports found"
  exit 0
fi

FROM_DIR="$(dirname "$TARGET")"
resolved_count=0
skipped_count=0

while IFS= read -r imp; do
  resolved=$(resolve_import "$FROM_DIR" "$imp" 2>/dev/null) || true

  if [ -n "$resolved" ]; then
    resolved_count=$((resolved_count + 1))
    rel_resolved="${resolved#$PROJECT_ROOT/}"
    subheader "Import: $imp → $rel_resolved"

    # Extract exported signatures from the resolved file
    sigs=$(extract_signatures "$resolved")
    if [ -n "$sigs" ]; then
      echo "$sigs"
    else
      dim "  (no exported signatures found)"
    fi
  else
    skipped_count=$((skipped_count + 1))
    dim "  ⊘ $imp (external/unresolved)"
  fi
done <<< "$import_paths"

echo ""
dim "Resolved: $resolved_count | Skipped (external): $skipped_count"
