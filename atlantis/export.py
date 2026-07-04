"""Brain-pack export: Data/chunks/*.md -> one sgc-brain/1 JSON file.

Maps salience-annotated chunk files (YAML frontmatter + body) onto the
brain-pack contract consumed by SGC (`brain_pack_contract` in the SGC repo's
plugin-brains spec). Only lexical fields cross the boundary — text, summary,
topics, flattened aliases — never Chroma embeddings. Only `status: active`
chunks are exported.

`source.stub` is read from index.json's `backend` field (stamped by ingest),
so provenance reflects how the corpus was actually built rather than trusting
a flag the operator has to remember.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

PACK_SCHEMA = "sgc-brain/1"
ATLANTIS_SCHEMA = "atlantis-salience-v1"
PACK_ID_RE = re.compile(r"^[a-z0-9-]{1,64}$")
MAX_CHUNK_CHARS = 8000


def parse_chunk_file(path: Path) -> tuple[dict[str, Any], str]:
    """Split a chunk .md into (frontmatter dict, stripped body).

    Splits on the first fence pair only — chunk bodies may legitimately
    contain their own ``---`` lines.
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path.name}: missing frontmatter fence")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError(f"{path.name}: unterminated frontmatter fence")
    fm = yaml.safe_load(text[4:end])
    if not isinstance(fm, dict):
        raise ValueError(f"{path.name}: frontmatter is not a mapping")
    return fm, text[end + 5 :].strip()


def flatten_aliases(aliases: Any) -> list[str]:
    """Flatten the aliases dict: every key AND value as separate strings."""
    out: list[str] = []
    if isinstance(aliases, dict):
        for key, value in aliases.items():
            for item in (key, value):
                s = str(item).strip()
                if s:
                    out.append(s)
    return out


def chunk_entry(fm: dict[str, Any], body: str) -> dict[str, Any]:
    """Map one chunk's frontmatter + body onto the pack chunk shape."""
    nav = fm.get("navigation") or {}
    return {
        "id": str(fm.get("chunk_id", "")),
        "title": str(fm.get("document_title", "")),
        "text": body,
        "summary": str(fm.get("summary", "")),
        "topics": [t["topic"] for t in fm.get("topics") or [] if t.get("topic")],
        "aliases": flatten_aliases(fm.get("aliases")),
        "source": {
            "file": str(fm.get("source_file", "")),
            "doc": str(fm.get("document_slug", "")),
            "position": int(nav.get("current") or 0),
        },
        "tokens": int(fm.get("tokens") or 0),
    }


def read_backend_stub(index_json: Path) -> bool:
    """True only when index.json records a stub-built corpus."""
    try:
        data = json.loads(index_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return data.get("backend") == "StubClassifier"


def build_pack(
    chunks_dir: Path,
    *,
    pack_id: str,
    name: str,
    description: str,
    version: str,
    stub: bool,
    built_at: str,
) -> dict[str, Any]:
    """Assemble a pack dict from every active chunk file in chunks_dir."""
    chunks: list[dict[str, Any]] = []
    for path in sorted(chunks_dir.glob("*.md")):
        fm, body = parse_chunk_file(path)
        if fm.get("status") != "active":
            continue
        chunks.append(chunk_entry(fm, body))
    return {
        "schema": PACK_SCHEMA,
        "id": pack_id,
        "name": name,
        "description": description,
        "version": version,
        "built_at": built_at,
        "source": {"tool": "atlantis", "schema": ATLANTIS_SCHEMA, "stub": stub},
        "chunks": chunks,
    }


def validate_pack(pack: dict[str, Any]) -> list[str]:
    """Return human-readable problems (empty = valid) against sgc-brain/1."""
    problems: list[str] = []
    if pack.get("schema") != PACK_SCHEMA:
        problems.append(f"bad schema {pack.get('schema')!r}")
    if not PACK_ID_RE.match(pack.get("id") or ""):
        problems.append(f"pack id {pack.get('id')!r} not [a-z0-9-]{{1,64}}")
    for field in ("name", "description", "version", "built_at"):
        if not isinstance(pack.get(field), str):
            problems.append(f"{field} is not a string")
    if not pack.get("chunks"):
        problems.append("no active chunks to export")
    seen_ids: set[str] = set()
    for c in pack.get("chunks") or []:
        cid = c.get("id") or "?"
        if not c.get("id"):
            problems.append("chunk with empty id")
        elif cid in seen_ids:
            problems.append(f"{cid}: duplicate chunk id")
        seen_ids.add(cid)
        n = len(c.get("text") or "")
        if not 1 <= n <= MAX_CHUNK_CHARS:
            problems.append(f"{cid}: text length {n} outside 1..{MAX_CHUNK_CHARS}")
        if not c.get("title"):
            problems.append(f"{cid}: empty title")
    return problems


def write_pack(pack: dict[str, Any], out_path: Path) -> None:
    """Write the pack as UTF-8 JSON. allow_nan=False enforces the contract."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(pack, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
