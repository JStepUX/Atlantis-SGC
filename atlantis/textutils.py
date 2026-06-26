"""Text utilities: tokenization for TF-IDF, stopwords, slugs, token estimation.

Deliberately dependency-free and deterministic — the same input always yields
the same tokens, so salience scores and the index are reproducible across runs.
"""

from __future__ import annotations

import re
import unicodedata

# Compact English stopword set. Kept inline so ingest needs no NLTK download
# and stays deterministic. Domain-agnostic by design.
STOPWORDS: frozenset[str] = frozenset(
    """
    a an the and or but if then else when while of to in on at by for with from
    into onto over under again further once here there all any both each few more
    most other some such no nor not only own same so than too very can will just
    is are was were be been being have has had having do does did doing would
    should could ought i you he she it we they them this that these those my your
    his her its our their what which who whom whose how why where as up down out
    off about above below between through during before after about also however
    therefore thus hence within without across per via etc among toward towards
    """.split()
)

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'+-]*")


def slugify(text: str) -> str:
    """Lowercase ascii slug: 'Brazilian Jiu-Jitsu' -> 'brazilian-jiu-jitsu'."""
    norm = unicodedata.normalize("NFKD", text)
    norm = norm.encode("ascii", "ignore").decode("ascii")
    norm = norm.lower()
    norm = re.sub(r"[^a-z0-9]+", "-", norm)
    return norm.strip("-")


def tokenize(text: str) -> list[str]:
    """Lowercased word tokens, no stopword removal (caller decides)."""
    return [m.group(0).lower() for m in _WORD_RE.finditer(text)]


def content_terms(text: str) -> list[str]:
    """Tokens with stopwords and pure-numeric/very-short tokens removed.

    This is the term stream used for TF-IDF and information-density.
    """
    out: list[str] = []
    for tok in tokenize(text):
        if tok in STOPWORDS:
            continue
        if len(tok) < 2:
            continue
        out.append(tok)
    return out


def estimate_tokens(text: str) -> int:
    """Fast offline token estimate.

    Blends a character heuristic (~4 chars/token, good for prose) with a word
    heuristic (~1.3 tokens/word, good for short/technical text) and takes the
    larger so budgeting errs conservative. Replace with the KoboldCPP token
    endpoint (tokens.mode = "kobold") when exactness matters.
    """
    if not text:
        return 0
    chars = len(text)
    words = len(_WORD_RE.findall(text))
    by_chars = round(chars / 4)
    by_words = round(words * 1.3)
    return max(1, by_chars, by_words)
