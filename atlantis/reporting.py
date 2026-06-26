"""Progress reporting for ingest.

The pipeline emits *structured* progress events to a ``Reporter`` rather than
printing strings directly, so the same run can drive a plain console log, a
silent test sink, or the live Rich dashboard (and, later, a web frontend) without
the pipeline knowing which.

Reporters:
* ``NullReporter``    — silent (tests).
* ``ConsoleReporter`` — line-by-line prints (piped output, --plain, non-TTY).
* ``RichReporter``    — live terminal dashboard (see dashboard.py).

Canonical stage order is ``STAGES``; the dashboard renders one row per stage.
"""

from __future__ import annotations

from typing import Iterable

# (key, display label) — order defines dashboard row order.
STAGES: list[tuple[str, str]] = [
    ("discover", "Discover"),
    ("chunk", "Chunk"),
    ("salience", "Salience"),
    ("classify", "Classify"),
    ("index", "Index"),
    ("chroma", "Chroma"),
]
STAGE_KEYS = {k for k, _ in STAGES}


class Reporter:
    """No-op base. Subclasses override what they care about."""

    def __enter__(self) -> "Reporter":
        return self

    def __exit__(self, *exc) -> None:
        return None

    def set_context(self, corpus: str = "", backend: str = "") -> None: ...
    def stage(self, key: str, status: str, detail: str = "") -> None: ...
    def classify_total(self, total: int) -> None: ...
    def classify_step(
        self, chunk_id: str, chunk_type: str, confidence: float, fallback: bool
    ) -> None: ...
    def note_validation(self, count: int) -> None: ...
    def info(self, msg: str) -> None: ...


class NullReporter(Reporter):
    """Silent."""


class ConsoleReporter(Reporter):
    """Plain line-oriented output (the original CLI behavior)."""

    def __init__(self) -> None:
        self._classify_total = 0
        self._classify_done = 0

    def set_context(self, corpus: str = "", backend: str = "") -> None:
        if corpus:
            print(f"Corpus: {corpus}")
        if backend:
            print(f"Classifier: {backend}")

    def stage(self, key: str, status: str, detail: str = "") -> None:
        if status == "start":
            print(f"[{key}] ...")
        elif status == "done":
            tail = f" {detail}" if detail else ""
            print(f"[{key}] done{tail}")

    def classify_total(self, total: int) -> None:
        self._classify_total = total
        self._classify_done = 0
        print(f"Classifying {total} chunk(s)...")

    def classify_step(
        self, chunk_id: str, chunk_type: str, confidence: float, fallback: bool
    ) -> None:
        self._classify_done += 1
        n, total = self._classify_done, self._classify_total
        if n % 10 == 0 or n == total:
            print(f"  classified {n}/{total}")

    def note_validation(self, count: int) -> None:
        if count:
            print(f"Validation: {count} problem(s)")
        else:
            print("Validation: all chunks valid.")

    def info(self, msg: str) -> None:
        print(f"  {msg}")


def make_reporter(plain: bool = False, corpus: str = "") -> Reporter:
    """Pick a reporter: Rich on a real TTY, plain otherwise."""
    import sys

    if plain or not sys.stdout.isatty():
        return ConsoleReporter()
    try:
        from .dashboard import RichReporter

        return RichReporter(corpus=corpus)
    except Exception:
        # Any rich/terminal issue -> never let the UI break ingest.
        return ConsoleReporter()


def join(parts: Iterable[str]) -> str:
    return "  ".join(p for p in parts if p)
