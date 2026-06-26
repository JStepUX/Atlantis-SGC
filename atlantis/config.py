"""Configuration loading for the Atlantis pipeline.

Reads config/atlantis.toml (stdlib tomllib) and overlays defaults so the
pipeline runs even with a partial or missing config file. All filesystem
paths are resolved relative to the project root.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Project root = parent of the `atlantis` package directory.
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT / "config" / "atlantis.toml"


@dataclass
class PathsConfig:
    raw_dir: Path
    chunks_dir: Path
    chroma_dir: Path
    index_json: Path
    index_md: Path


@dataclass
class ChunkingConfig:
    target_tokens: int = 320
    max_tokens: int = 480
    min_tokens: int = 40
    respect_headings: bool = True


@dataclass
class ModelConfig:
    base_url: str = "http://localhost:5001/v1"
    model: str = "koboldcpp"
    api_key: str = ""
    temperature: float = 0.2
    max_tokens: int = 1024
    timeout: int = 120
    retries: int = 2


@dataclass
class EmbeddingsConfig:
    collection_name: str = "atlantis"
    alias_strategy: str = "append"  # append | prepend | none


@dataclass
class IndexConfig:
    root_min_count: int = 3
    root_min_distinct: int = 2
    root_top_k: int = 8
    sibling_threshold: float = 0.30


@dataclass
class ProvenanceConfig:
    source_type: str = "human-authored"
    default_authority: str = "canonical"
    default_confidence: float = 0.8
    author: str = ""
    original_source: str = ""


@dataclass
class TemporalConfig:
    decay_class: str = "evergreen"


@dataclass
class SalienceConfig:
    related_max: int = 2
    related_min_overlap: float = 0.20


@dataclass
class TokensConfig:
    mode: str = "estimate"  # estimate | kobold


@dataclass
class Config:
    paths: PathsConfig
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    embeddings: EmbeddingsConfig = field(default_factory=EmbeddingsConfig)
    index: IndexConfig = field(default_factory=IndexConfig)
    provenance: ProvenanceConfig = field(default_factory=ProvenanceConfig)
    temporal: TemporalConfig = field(default_factory=TemporalConfig)
    salience: SalienceConfig = field(default_factory=SalienceConfig)
    tokens: TokensConfig = field(default_factory=TokensConfig)

    @property
    def root(self) -> Path:
        return ROOT


def _resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else (ROOT / path)


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    return dict(data.get(name, {}) or {})


def load_config(path: str | Path | None = None) -> Config:
    """Load configuration, overlaying file values onto dataclass defaults."""
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    data: dict[str, Any] = {}
    if cfg_path.exists():
        with open(cfg_path, "rb") as fh:
            data = tomllib.load(fh)

    p = _section(data, "paths")
    paths = PathsConfig(
        raw_dir=_resolve(p.get("raw_dir", "Data/raw")),
        chunks_dir=_resolve(p.get("chunks_dir", "Data/chunks")),
        chroma_dir=_resolve(p.get("chroma_dir", "Data/chroma")),
        index_json=_resolve(p.get("index_json", "Data/index.json")),
        index_md=_resolve(p.get("index_md", "Data/index.md")),
    )

    return Config(
        paths=paths,
        chunking=ChunkingConfig(**_section(data, "chunking")),
        model=ModelConfig(**_section(data, "model")),
        embeddings=EmbeddingsConfig(**_section(data, "embeddings")),
        index=IndexConfig(**_section(data, "index")),
        provenance=ProvenanceConfig(**_section(data, "provenance")),
        temporal=TemporalConfig(**_section(data, "temporal")),
        salience=SalienceConfig(**_section(data, "salience")),
        tokens=TokensConfig(**_section(data, "tokens")),
    )
