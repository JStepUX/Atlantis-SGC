#!/usr/bin/env bash
# _common.sh — Shared utilities for agent scripts (Python stack)
# Source this file: source "$(dirname "$0")/_common.sh"
#
# Adapted from the AIX default (TypeScript) stack to Python: import resolution,
# import extraction, and signature extraction use Python's `ast` module (more
# accurate than regex/awk), so they understand `from .x import y`, decorators,
# class methods, and multi-line signatures.

set -euo pipefail
export MSYS_NO_PATHCONV=1

# ── Project root (two levels up from scripts/agent/) ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# ── Python interpreter ──
PY="${PYTHON:-python}"
command -v "$PY" >/dev/null 2>&1 || PY="python3"

# ── Exclude patterns for find/grep (Python noise dirs + generated data) ──
EXCLUDE_DIRS="__pycache__|\.git|\.venv|venv|\.pytest_cache|\.mypy_cache|\.ruff_cache|build|dist|\.egg-info|node_modules|Data/chroma|Data/chunks"
GREP_EXCLUDE="--exclude-dir=__pycache__ --exclude-dir=.git --exclude-dir=.venv --exclude-dir=venv --exclude-dir=.pytest_cache --exclude-dir=.mypy_cache --exclude-dir=.ruff_cache --exclude-dir=build --exclude-dir=dist --exclude-dir=node_modules"

# ── Colors (disabled when piped) ──
if [ -t 1 ]; then
  BOLD='\033[1m'; DIM='\033[2m'; CYAN='\033[36m'; GREEN='\033[32m'
  YELLOW='\033[33m'; RED='\033[31m'; RESET='\033[0m'
else
  BOLD='' DIM='' CYAN='' GREEN='' YELLOW='' RED='' RESET=''
fi

header()    { echo -e "\n${BOLD}${CYAN}═══ $1 ═══${RESET}"; }
subheader() { echo -e "\n${GREEN}── $1 ──${RESET}"; }
dim()       { echo -e "${DIM}$1${RESET}"; }
warn()      { echo -e "${YELLOW}⚠ $1${RESET}" >&2; }
err()       { echo -e "${RED}✗ $1${RESET}" >&2; }

# ── resolve_import(from_dir, module) ──
# Resolves a Python import to an absolute .py file path.
# Handles relative imports ('.config', '..pkg.mod') and first-party absolute
# imports ('atlantis.config'). Returns 1 for stdlib/third-party (unresolved).
resolve_import() {
  local from_dir="$1"
  local mod="$2"
  local base=""

  if [[ "$mod" == .* ]]; then
    local dots="${mod%%[!.]*}"   # leading dots
    local rest="${mod#"$dots"}"  # remainder after the dots
    local level=${#dots}
    local dir="$from_dir"
    local i
    for ((i = 1; i < level; i++)); do dir="$(dirname "$dir")"; done
    if [ -n "$rest" ]; then
      base="$dir/${rest//.//}"
    else
      base="$dir"
    fi
  else
    # Absolute: only first-party modules that physically exist under the root.
    base="$PROJECT_ROOT/${mod//.//}"
  fi

  local cand
  for cand in "$base.py" "$base/__init__.py"; do
    if [ -f "$cand" ]; then echo "$cand"; return 0; fi
  done
  return 1
}

# ── extract_imports(file) ──
# Emits imported module tokens, one per line (e.g. 'numpy', '.config',
# 'atlantis.salience'). Uses ast so it never misreads strings as imports.
extract_imports() {
  local file="$1"
  "$PY" - "$file" <<'PY' 2>/dev/null || true
import ast, sys, os, re
sys.stdout.reconfigure(newline="\n")  # avoid \r\n on Windows -> clean tokens
p = sys.argv[1]
if os.name == "nt" and re.match(r"^/[A-Za-z]/", p):  # MSYS /c/... -> C:/...
    p = p[1] + ":" + p[2:]
try:
    tree = ast.parse(open(p, encoding="utf-8").read())
except Exception:
    sys.exit(0)
for n in ast.walk(tree):
    if isinstance(n, ast.Import):
        for a in n.names:
            print(a.name)
    elif isinstance(n, ast.ImportFrom):
        print("." * (n.level or 0) + (n.module or ""))
PY
}

# ── extract_signatures(file) ──
# Prints top-level functions and classes (with their method signatures and
# first docstring line), plus module-level CONSTANTS and annotated names.
# Body lines are omitted — signatures only. Uses ast for accuracy.
extract_signatures() {
  local file="$1"
  "$PY" - "$file" <<'PY' 2>/dev/null || true
import ast, sys, os, re
sys.stdout.reconfigure(newline="\n")  # avoid \r\n on Windows -> clean tokens
p = sys.argv[1]
if os.name == "nt" and re.match(r"^/[A-Za-z]/", p):  # MSYS /c/... -> C:/...
    p = p[1] + ":" + p[2:]
try:
    src = open(p, encoding="utf-8").read()
    lines = src.splitlines()
    tree = ast.parse(src)
except Exception:
    sys.exit(0)

def sig(node):
    start = node.lineno - 1
    end = node.body[0].lineno - 1 if node.body else node.lineno
    seg_lines = lines[start:end]
    if not seg_lines:
        return lines[start].split(":", 1)[0].strip() + ":"
    seg = " ".join(l.strip() for l in seg_lines).rstrip()
    if not seg.endswith(":"):
        seg = seg.rstrip(":") + ":"
    return seg

def doc1(node):
    d = ast.get_docstring(node)
    return ("    " + d.strip().splitlines()[0][:100]) if d else ""

for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for d in node.decorator_list:
            print("@" + ast.unparse(d))
        print(sig(node))
        if doc1(node): print(doc1(node))
        print()
    elif isinstance(node, ast.ClassDef):
        for d in node.decorator_list:
            print("@" + ast.unparse(d))
        bases = ", ".join(ast.unparse(b) for b in node.bases)
        print(f"class {node.name}" + (f"({bases})" if bases else "") + ":")
        if doc1(node): print(doc1(node))
        for sub in node.body:
            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                print("    " + sig(sub))
        print()
    elif isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and (t.id.isupper() or t.id.startswith("__")):
                print(f"{t.id} = ...")
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        print(f"{node.target.id}: {ast.unparse(node.annotation)}")
PY
}
