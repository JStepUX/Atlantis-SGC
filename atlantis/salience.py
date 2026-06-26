"""Corpus-level TF-IDF salience pass.

Fills the salience signals Atlantis computes deterministically:

* ``information_density`` — unique content terms / total tokens, per chunk
  (local; no corpus needed). Schema: "(unique non-stopword terms / total tokens)".
* ``lexical_distinctiveness`` — how far a chunk's TF-IDF vector sits from the
  corpus centroid (cosine distance), min-max normalised across the corpus to
  0..1. High = rare/distinctive terminology.

``specificity`` and ``standalone`` are NOT computed here — specificity is derived
from the model's topic depths (see schema.py) and standalone comes from the model.

The TF-IDF matrix built here is also reused by the index builder for sibling
similarity, so we expose the vectorizer rather than hiding it.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from .models import Chunk
from .textutils import content_terms


@dataclass
class TfidfModel:
    """A fitted TF-IDF space over a fixed list of chunks."""

    vocab: dict[str, int]
    idf: np.ndarray                       # shape (V,)
    matrix: np.ndarray                    # shape (N, V), L2-normalised rows
    chunk_ids: list[str]
    term_lists: dict[str, list[str]] = field(default_factory=dict)

    def vector_for_terms(self, terms: list[str]) -> np.ndarray:
        """Project an arbitrary term list into the fitted space (L2-normalised)."""
        vec = np.zeros(len(self.vocab), dtype=np.float64)
        if not terms:
            return vec
        counts = Counter(t for t in terms if t in self.vocab)
        if not counts:
            return vec
        total = sum(counts.values())
        for term, c in counts.items():
            j = self.vocab[term]
            vec[j] = (c / total) * self.idf[j]
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec


def fit_tfidf(chunks: list[Chunk]) -> TfidfModel:
    """Fit a TF-IDF model over the chunk bodies."""
    term_lists = {c.chunk_id: content_terms(c.body) for c in chunks}

    vocab: dict[str, int] = {}
    df: Counter[str] = Counter()
    for terms in term_lists.values():
        for term in set(terms):
            df[term] += 1
            if term not in vocab:
                vocab[term] = len(vocab)

    n_docs = max(1, len(chunks))
    v = len(vocab)
    idf = np.zeros(v, dtype=np.float64)
    for term, j in vocab.items():
        # Smoothed idf; +1 keeps ubiquitous terms from going to exactly zero.
        idf[j] = math.log((1 + n_docs) / (1 + df[term])) + 1.0

    matrix = np.zeros((len(chunks), v), dtype=np.float64)
    for i, c in enumerate(chunks):
        terms = term_lists[c.chunk_id]
        if not terms:
            continue
        counts = Counter(terms)
        total = sum(counts.values())
        for term, cnt in counts.items():
            j = vocab[term]
            matrix[i, j] = (cnt / total) * idf[j]
        norm = np.linalg.norm(matrix[i])
        if norm > 0:
            matrix[i] /= norm

    return TfidfModel(
        vocab=vocab,
        idf=idf,
        matrix=matrix,
        chunk_ids=[c.chunk_id for c in chunks],
        term_lists=term_lists,
    )


def _information_density(terms: list[str], tokens: int) -> float:
    if tokens <= 0:
        return 0.0
    return min(1.0, len(set(terms)) / tokens)


def compute_salience(chunks: list[Chunk], model: TfidfModel) -> None:
    """Populate lexical_distinctiveness and information_density in place."""
    # information_density (local, per chunk)
    for c in chunks:
        terms = model.term_lists.get(c.chunk_id, content_terms(c.body))
        c.information_density = round(_information_density(terms, c.tokens), 3)

    # lexical_distinctiveness via cosine distance from the corpus centroid.
    if model.matrix.shape[0] == 0 or model.matrix.shape[1] == 0:
        for c in chunks:
            c.lexical_distinctiveness = 0.0
        return

    centroid = model.matrix.mean(axis=0)
    cnorm = np.linalg.norm(centroid)
    if cnorm > 0:
        centroid = centroid / cnorm

    sims = model.matrix @ centroid          # cosine sim to centroid (rows are unit)
    distances = 1.0 - sims                   # distinctiveness, unnormalised

    dmin, dmax = float(distances.min()), float(distances.max())
    spread = dmax - dmin
    for i, c in enumerate(chunks):
        if spread > 1e-9:
            val = (distances[i] - dmin) / spread
        else:
            val = 0.0
        c.lexical_distinctiveness = round(float(val), 3)
