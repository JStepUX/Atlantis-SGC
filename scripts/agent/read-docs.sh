#!/usr/bin/env bash
# read-docs.sh — RTFM tool for agents working with post-cutoff Python packages
# Usage: read-docs.sh <package> | --audit | --index | --stale
#
# Surfaces vendored docs, Context7 pointers, and training-familiarity warnings.
# Reconciled from the AIX default (npm/package.json) stack to Python: it reads
# INSTALLED versions via importlib.metadata and checks them against the cutoff
# registry below. Update CUTOFF_REGISTRY / CONTEXT7_IDS when the stack changes.

source "$(dirname "$0")/_common.sh"

VENDOR_DIR="$PROJECT_ROOT/docs/vendor"
REF_DIR="$VENDOR_DIR/reference"

# ── Training cutoff registry ──
# package:threshold_version:familiarity. Versions AT OR ABOVE threshold are
# outside reliable training data. Atlantis's actual runtime deps.
CUTOFF_REGISTRY=(
  "chromadb:1.0.0:low"
  "onnxruntime:1.20.0:medium"
  "numpy:2.0.0:medium"
  "anthropic:0.40.0:medium"
  "pyyaml:6.0.0:high"
  "requests:2.31.0:high"
)

# ── Vendored docs (package → file under docs/vendor/) ──
# None yet for the Python stack — the JS defaults (react/tailwind/drizzle/
# anthropic-sdk) were dropped at install. Add entries when you vendor a doc.
declare -A VENDORED_DOCS=()

# ── Context7 library hints ──
declare -A CONTEXT7_IDS=(
  ["chromadb"]="resolve: chromadb"
  ["chroma"]="resolve: chromadb"
  ["numpy"]="resolve: numpy"
  ["anthropic"]="resolve: anthropic"
  ["requests"]="resolve: requests"
  ["pyyaml"]="resolve: pyyaml"
  ["yaml"]="resolve: pyyaml"
)

# ── Packages with neither vendored docs nor known Context7 coverage ──
declare -A NOT_IN_CONTEXT7=(
  ["onnxruntime"]="1"
)

pad_version() { local v="$1"; while [ "$(echo "$v" | tr -cd '.' | wc -c)" -lt 2 ]; do v="${v}.0"; done; echo "$v"; }
version_gte() {
  local v1 v2; v1=$(echo "$1" | sed 's/^[\^~>=]*//'); v2=$(echo "$2" | sed 's/^[\^~>=]*//')
  v1=$(pad_version "$v1"); v2=$(pad_version "$v2")
  [ "$(printf '%s\n%s' "$v2" "$v1" | sort -V | head -1)" = "$v2" ]
}

# Installed version via importlib.metadata (authoritative — what's actually loaded).
get_version() {
  "$PY" - "$1" <<'PY' 2>/dev/null || true
import sys
from importlib.metadata import version, PackageNotFoundError
try:
    print(version(sys.argv[1]))
except PackageNotFoundError:
    pass
PY
}

show_index() {
  header "Vendored Documentation"
  subheader "Durable API Reference (docs/vendor/reference/)"
  local ref_count=0
  if [ -d "$REF_DIR" ]; then
    for f in "$REF_DIR"/*.md; do
      [ -f "$f" ] || continue
      [[ "$(basename "$f")" == "README.md" ]] && continue
      ref_count=$((ref_count + 1))
      echo -e "  ${CYAN}$(basename "$f")${RESET}"
    done
  fi
  [ "$ref_count" -eq 0 ] && dim "    (none vendored yet — Context7 covers the deps below)"
  subheader "Context7 MCP (live docs)"
  echo -e "  ${GREEN}Available:${RESET} chromadb, numpy, anthropic, requests, pyyaml"
  echo -e "  ${RED}Not indexed:${RESET} onnxruntime"
}

audit_packages() {
  header "Post-Cutoff Package Audit (installed versions)"
  echo -e "${DIM}Checking importlib.metadata versions against the cutoff registry...${RESET}\n"
  local warnings=0 vendored=0 context7_ok=0 exposed=0
  for entry in "${CUTOFF_REGISTRY[@]}"; do
    IFS=: read -r pkg threshold familiarity <<< "$entry"
    local installed; installed=$(get_version "$pkg")
    [ -z "$installed" ] && continue
    if version_gte "$installed" "$threshold"; then
      warnings=$((warnings + 1))
      local key; key=$(echo "$pkg" | tr '[:upper:]' '[:lower:]')
      local doc_rel="${VENDORED_DOCS[$key]:-}"
      if [ -n "$doc_rel" ] && [ -f "$VENDOR_DIR/$doc_rel" ]; then
        vendored=$((vendored + 1))
        echo -e "  ${GREEN}$pkg${RESET} $installed (${familiarity})"
        echo -e "    ${GREEN}Vendored docs:${RESET} docs/vendor/$doc_rel"; continue
      fi
      local c7="${CONTEXT7_IDS[$key]:-}"
      if [ -n "$c7" ]; then
        context7_ok=$((context7_ok + 1))
        echo -e "  ${YELLOW}$pkg${RESET} $installed (${familiarity})"
        echo -e "    ${YELLOW}Use Context7:${RESET} $c7"; continue
      fi
      exposed=$((exposed + 1))
      echo -e "  ${RED}$pkg${RESET} $installed (${familiarity})"
      echo -e "    ${RED}NO DOCS AND NOT IN CONTEXT7 — agent is flying blind${RESET}"
    fi
  done
  echo ""
  header "Summary"
  echo -e "  Post-cutoff packages:     ${BOLD}$warnings${RESET}"
  echo -e "  With vendored docs:       ${GREEN}$vendored${RESET}"
  echo -e "  Deferred to Context7 MCP: ${YELLOW}$context7_ok${RESET}"
  echo -e "  ${RED}FLYING BLIND (no docs):   $exposed${RESET}"
  if [ "$context7_ok" -gt 0 ]; then
    echo ""
    dim "Context7-deferred packages are NOT a gap. Query at the call site:"
    dim "  mcp__..._Context7__resolve-library-id(libraryName=\"<pkg>\", query=\"…\")"
    dim "  mcp__..._Context7__query-docs(libraryId=\"<id>\", query=\"…\")"
  fi
  return "$exposed"
}

show_stale() {
  header "Packages Without Documentation Coverage"
  local matches; matches=$(audit_packages 2>&1 | grep -B1 "NO DOCS AND NOT IN CONTEXT7" || true)
  if [ -n "$matches" ]; then echo "$matches"; else dim "  (none — every post-cutoff package has Context7 coverage)"; fi
}

search_package() {
  local query="$1"; local q; q=$(echo "$query" | tr '[:upper:]' '[:lower:]')
  header "readDocs: $query"
  local familiarity=""
  for entry in "${CUTOFF_REGISTRY[@]}"; do
    IFS=: read -r pkg threshold fam <<< "$entry"
    local pl; pl=$(echo "$pkg" | tr '[:upper:]' '[:lower:]')
    if [[ "$pl" == *"$q"* || "$q" == *"$pl"* ]]; then
      familiarity="$fam"
      local inst; inst=$(get_version "$pkg")
      echo -e "  Installed: ${BOLD}${inst:-not installed}${RESET}   Training familiarity: ${BOLD}$fam${RESET}"
      case "$fam" in
        low)    echo -e "  ${RED}⚠ EXTERNAL DOCS REQUIRED — agent will hallucinate without reference${RESET}" ;;
        medium) echo -e "  ${YELLOW}⚠ Proceed with caution — knows concepts, may miss new idioms${RESET}" ;;
        high)   echo -e "  ${GREEN}✓ Well within training data${RESET}" ;;
      esac
      break
    fi
  done
  [ -z "$familiarity" ] && echo -e "  ${DIM}Not in cutoff registry — likely within training data${RESET}"

  local mapped="${VENDORED_DOCS[$q]:-}"
  if [ -n "$mapped" ] && [ -f "$VENDOR_DIR/$mapped" ]; then
    subheader "Vendored Documentation"; echo -e "  ${CYAN}docs/vendor/$mapped${RESET}"
  fi
  local c7="${CONTEXT7_IDS[$q]:-}"
  if [ -n "$c7" ]; then
    subheader "Context7 MCP"; echo -e "  $c7"
    echo -e "  Use: resolve-library-id then query-docs"
  elif [ -n "${NOT_IN_CONTEXT7[$q]:-}" ]; then
    subheader "Context7 MCP"; echo -e "  ${RED}NOT INDEXED — vendored docs are your only reference${RESET}"
  fi
}

case "${1:-}" in
  --index|-i) show_index ;;
  --audit|-a) audit_packages ;;
  --stale|-s) show_stale ;;
  --help|-h|"")
    echo "read-docs.sh — RTFM tool for agents working outside training data"
    echo ""
    echo "Usage:"
    echo "  read-docs.sh <package>   Check familiarity + surface docs for a dep"
    echo "  read-docs.sh --audit     Check installed deps against the cutoff registry"
    echo "  read-docs.sh --stale     Flying blind: post-cutoff deps with no coverage"
    echo "  read-docs.sh --index     List vendored docs + Context7 coverage"
    ;;
  *) search_package "$1" ;;
esac
