"""Atlantis — the brain-pack compiler for the sibling SGC repo.

Processes raw documents into frontmatter-annotated chunk files (Atlantis
Salience Schema v1.0) and exports them as sgc-brain/1 knowledge packs
(`python -m atlantis export`). Lexical fields only cross that contract.
The original vector tail (TF-IDF salience, categorical index, Chroma/MiniLM)
is dormant Phase 2b infrastructure behind `ingest --full`.
"""

__version__ = "1.0.0"
