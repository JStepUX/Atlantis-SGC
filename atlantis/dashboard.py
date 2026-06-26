"""Live Rich terminal dashboard for ingest progress.

A single ``Live`` drives a self-rendering ``RichReporter`` (it implements
``__rich__``). ``auto_refresh`` runs Rich's own refresh thread, so the
Classify elapsed/ETA timer keeps ticking smoothly even while the main thread is
blocked inside a multi-second model call.

time.monotonic() is used only for elapsed/ETA display (normal process runtime,
not the workflow sandbox), so it is available here.
"""

from __future__ import annotations

import sys
import time

from rich.console import Console, Group
from rich.live import Live
from rich.rule import Rule
from rich.text import Text

from .reporting import STAGES, Reporter

_LABEL_W = 10
_BAR_W = 22

# Glyph sets. Pretty requires a UTF-8 capable console; the ASCII set is a safe
# fallback for legacy Windows code pages (cp1252/cp437) that would otherwise
# raise UnicodeEncodeError mid-render.
_GLYPHS = {
    "pretty": {
        "wait": ("·", "dim"),
        "run": ("◐", "bold yellow"),
        "done": ("✔", "bold green"),
        "fill": "━",
        "cap": "╸",
        "empty": "·",
        "arrow": "▸",
        "rule": "─",
    },
    "ascii": {
        "wait": (".", "dim"),
        "run": (">", "bold yellow"),
        "done": ("*", "bold green"),
        "fill": "#",
        "cap": "",
        "empty": "-",
        "arrow": ">",
        "rule": "-",
    },
}


def _unicode_ok() -> bool:
    """True if stdout can encode the pretty glyphs."""
    enc = (getattr(sys.stdout, "encoding", "") or "").lower()
    if "utf" in enc:
        return True
    try:
        "━◐✔▸".encode(enc or "ascii")
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def _fmt_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


class RichReporter(Reporter):
    def __init__(self, corpus: str = "") -> None:
        self.corpus = corpus
        self.backend = ""
        # Prefer UTF-8 so the pretty glyphs work on Windows consoles whose
        # default code page (cp1252/cp437) would otherwise force the ASCII set.
        # Guarded: if it fails we simply fall back to ASCII glyphs below.
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass
        self.console = Console()
        pretty = _unicode_ok()
        self.g = _GLYPHS["pretty" if pretty else "ascii"]
        self._sep = "  ·  " if pretty else "  -  "
        self.live: Live | None = None

        self._status: dict[str, str] = {k: "wait" for k, _ in STAGES}
        self._detail: dict[str, str] = {k: "" for k, _ in STAGES}

        self._cls_total = 0
        self._cls_done = 0
        self._cls_start = 0.0
        self._last_id = ""
        self._last_type = ""
        self._last_conf = 0.0
        self._last_fallback = False
        self._fallbacks = 0
        self._validation = -1  # -1 = not yet known
        self._info = ""

    # --- lifecycle ---
    def __enter__(self) -> "RichReporter":
        self.live = Live(
            self, console=self.console, auto_refresh=True, refresh_per_second=8
        )
        self.live.start()
        return self

    def __exit__(self, *exc) -> None:
        if self.live is not None:
            self.live.stop()
            # Leave the final frame on screen.
            self.console.print(self)

    # --- events ---
    def set_context(self, corpus: str = "", backend: str = "") -> None:
        if corpus:
            self.corpus = corpus
        if backend:
            self.backend = backend

    def stage(self, key: str, status: str, detail: str = "") -> None:
        if key not in self._status:
            return
        if status == "start":
            self._status[key] = "run"
        elif status == "done":
            self._status[key] = "done"
        if detail:
            self._detail[key] = detail

    def classify_total(self, total: int) -> None:
        self._cls_total = total
        self._cls_done = 0
        self._cls_start = time.monotonic()

    def classify_step(
        self, chunk_id: str, chunk_type: str, confidence: float, fallback: bool
    ) -> None:
        self._cls_done += 1
        self._last_id = chunk_id
        self._last_type = chunk_type
        self._last_conf = confidence
        self._last_fallback = fallback
        if fallback:
            self._fallbacks += 1

    def note_validation(self, count: int) -> None:
        self._validation = count

    def info(self, msg: str) -> None:
        self._info = msg

    # --- rendering ---
    def _bar(self, frac: float) -> Text:
        frac = max(0.0, min(1.0, frac))
        filled = int(round(frac * _BAR_W))
        t = Text()
        if filled > 0:
            t.append(self.g["fill"] * filled, style="bold cyan")
        if filled < _BAR_W:
            if self.g["cap"]:
                t.append(self.g["cap"], style="cyan")
                t.append(self.g["empty"] * (_BAR_W - filled - 1), style="dim")
            else:
                t.append(self.g["empty"] * (_BAR_W - filled), style="dim")
        return t

    def _classify_meta(self) -> tuple[str, str]:
        """Return (counter_text, timer_text) for the classify row."""
        total = self._cls_total or 0
        done = self._cls_done
        pct = int(round(100 * done / total)) if total else 0
        counter = f"{done}/{total}  {pct}%"
        if done and self._cls_start:
            elapsed = time.monotonic() - self._cls_start
            rate = done / elapsed if elapsed > 0 else 0
            remaining = (total - done) / rate if rate > 0 else 0
            timer = f"elapsed {_fmt_time(elapsed)}{self._sep}eta {_fmt_time(remaining)}"
        else:
            timer = "starting..."
        return counter, timer

    def _stage_line(self, key: str, label: str) -> Text:
        status = self._status[key]
        icon, style = self.g[status]
        line = Text("  ")
        line.append(icon, style=style)
        line.append("  ")
        line.append(f"{label:<{_LABEL_W}}", style="bold" if status == "run" else "")

        if key == "classify" and status in ("run", "done"):
            frac = self._cls_done / self._cls_total if self._cls_total else 0.0
            counter, _ = self._classify_meta()
            line.append_text(self._bar(frac))
            line.append(f"  {counter}", style="cyan")
        else:
            detail = self._detail[key]
            if detail:
                line.append(detail, style="dim" if status != "done" else "green")
            elif status == "wait":
                line.append("waiting", style="dim")
        return line

    def __rich__(self) -> Group:
        parts: list = []

        title = Text("Atlantis Ingest", style="bold")
        for extra in (self.corpus, self.backend):
            if extra:
                title.append(self._sep, style="dim")
                title.append(extra, style="cyan")
        parts.append(title)
        parts.append(Rule(style="dim", characters=self.g["rule"]))

        for key, label in STAGES:
            parts.append(self._stage_line(key, label))
            if key == "classify" and self._status[key] == "run":
                _, timer = self._classify_meta()
                parts.append(Text(" " * (4 + _LABEL_W) + timer, style="dim"))

        parts.append(Rule(style="dim", characters=self.g["rule"]))

        # last classified
        if self._last_id:
            last = Text(f"  {self.g['arrow']} ", style="dim")
            last.append(self._last_id)
            last.append(f"  {self._last_type}", style="magenta")
            conf_style = "red" if self._last_fallback else "green"
            last.append(f"  conf {self._last_conf:.2f}", style=conf_style)
            parts.append(last)

        # counters
        val_txt = "-" if self._validation < 0 else f"{self._validation} issues"
        counters = Text("  ")
        counters.append("validation: ", style="dim")
        counters.append(val_txt, style="green" if self._validation == 0 else "yellow")
        counters.append("    fallbacks: ", style="dim")
        counters.append(str(self._fallbacks), style="green" if self._fallbacks == 0 else "red")
        parts.append(counters)

        if self._info:
            parts.append(Text(f"  {self._info}", style="dim italic"))

        return Group(*parts)
