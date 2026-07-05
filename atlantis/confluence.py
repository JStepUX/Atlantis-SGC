"""Confluence space-export importer: HTML pages -> clean markdown in raw_dir.

A Confluence "HTML space export" is a directory of per-page HTML files plus
attachments/styles/images. This module extracts each page's title and
`#main-content`, strips the chrome (breadcrumbs, page metadata, footers,
attachment/comment pageSections), and serializes the body to markdown ready
for the normal compile loop (`ingest` -> `export`). Text only — attachments
and images never cross (an image can't be lexically retrieved anyway).

Uses lxml for parsing (already present via the Phase 2b stack; the CLI gives
a clear install hint if missing). Pure stdlib otherwise.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .textutils import slugify

# Directories inside an export that never contain page HTML.
_SKIP_DIRS = {"attachments", "images", "styles"}

# Elements whose entire subtree is chrome, not content.
_STRIP_SELECTORS = [
    "script",
    "style",
    "div#breadcrumb-section",
    "div#breadcrumbs",
    "div.page-metadata",
    "div#footer",
    "div.pageSection",  # attachments / comments blocks appended by the exporter
]


@dataclass
class ImportReport:
    converted: int = 0
    skipped_stubs: int = 0
    skipped_files: list[str] = field(default_factory=list)
    out_files: list[Path] = field(default_factory=list)


def _inline_text(el) -> str:
    """Flatten an element to single-line text (for table cells / link labels)."""
    text = " ".join(el.itertext())
    return re.sub(r"\s+", " ", text).strip()


def _render_table(el) -> str:
    rows: list[list[str]] = []
    for tr in el.iter("tr"):
        cells = [
            _inline_text(c).replace("|", "\\|")
            for c in tr.iterchildren()
            if c.tag in ("td", "th")
        ]
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * width]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out) + "\n\n"


def _render(el, list_depth: int = 0, ordered: bool = False) -> str:
    """Recursive markdown serializer — pragmatic, not exhaustive."""
    tag = el.tag if isinstance(el.tag, str) else ""
    out: list[str] = []

    if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        text = _inline_text(el)
        return f"\n{'#' * int(tag[1])} {text}\n\n" if text else ""
    if tag == "table":
        return "\n" + _render_table(el)
    if tag == "pre":
        code = "".join(el.itertext()).strip("\n")
        return f"\n```\n{code}\n```\n\n" if code.strip() else ""
    if tag in ("ul", "ol"):
        items = []
        for i, li in enumerate(c for c in el.iterchildren() if c.tag == "li"):
            marker = f"{i + 1}." if tag == "ol" else "-"
            body = _render_children(li, list_depth + 1, tag == "ol").strip()
            body = re.sub(r"\n{2,}", "\n", body)
            indent = "  " * list_depth
            items.append(f"{indent}{marker} {body}")
        return "\n" + "\n".join(items) + "\n\n" if items else ""
    if tag == "a":
        label = _inline_text(el)
        href = el.get("href", "")
        tail = el.tail or ""
        if not label:
            return tail
        # Cross-page links inside the export point at sibling .html files —
        # keep the label only (chunk text wants prose, not dead local paths).
        if href.startswith(("http://", "https://")):
            return f"[{label}]({href})" + tail
        return label + tail
    if tag == "img":
        alt = el.get("alt", "").strip()
        return (f"({alt}) " if alt else "") + (el.tail or "")
    if tag == "br":
        return "\n" + (el.tail or "")
    if tag == "hr":
        return "\n\n---\n\n" + (el.tail or "")
    if tag in ("strong", "b"):
        text = _inline_text(el)
        return (f"**{text}**" if text else "") + (el.tail or "")
    if tag in ("em", "i"):
        text = _inline_text(el)
        return (f"*{text}*" if text else "") + (el.tail or "")
    if tag in ("code", "tt"):
        text = _inline_text(el)
        return (f"`{text}`" if text else "") + (el.tail or "")
    if tag == "p":
        body = _render_children(el, list_depth, ordered).strip()
        return f"{body}\n\n" if body else ""
    if tag == "blockquote":
        body = _render_children(el, list_depth, ordered).strip()
        quoted = "\n".join(f"> {line}" for line in body.splitlines())
        return f"\n{quoted}\n\n" if body else ""

    # Generic container (div/span/section/...): recurse.
    out.append(_render_children(el, list_depth, ordered))
    return "".join(out)


def _render_children(el, list_depth: int = 0, ordered: bool = False) -> str:
    parts: list[str] = [el.text or ""]
    for child in el.iterchildren():
        if isinstance(child.tag, str):
            parts.append(_render(child, list_depth, ordered))
            # .tail of handled-inline tags is consumed inside _render; block
            # tags' tails are picked up here.
            if child.tag not in ("a", "img", "br", "hr", "strong", "b", "em", "i", "code", "tt"):
                parts.append(child.tail or "")
        else:  # comment / PI
            parts.append(child.tail or "")
    return "".join(parts)


def convert_page(html_text: str, space_prefix_sep: str = " : ") -> tuple[str, str]:
    """One export page -> (title, markdown body). Raises on unparseable HTML."""
    from lxml import html as lhtml  # lazy: give the CLI a clean missing-dep hint

    doc = lhtml.fromstring(html_text)

    title = ""
    node = doc.find(".//title")
    if node is not None and node.text:
        title = node.text.strip()
        # "<Space Name> : <Page Title>" -> keep the page title.
        if space_prefix_sep in title:
            title = title.split(space_prefix_sep, 1)[1].strip()

    main = doc.get_element_by_id("main-content", None)
    if main is None:
        body_el = doc.find("body")
        main = body_el if body_el is not None else doc
    for sel in _STRIP_SELECTORS:
        if "#" in sel:
            tag, _, ident = sel.partition("#")
            hits = main.xpath(f".//{tag or '*'}[@id='{ident}']")
        elif "." in sel:
            tag, _, cls = sel.partition(".")
            hits = main.xpath(f".//{tag or '*'}[contains(@class,'{cls}')]")
        else:
            hits = main.xpath(f".//{sel}")
        for h in hits:
            h.getparent().remove(h)

    body = _render_children(main)
    body = re.sub(r"[ \t]+\n", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return title, body


def import_space_export(
    export_dir: Path,
    out_dir: Path,
    min_words: int = 10,
) -> ImportReport:
    """Convert every page in a Confluence HTML space export to markdown files.

    Files land as `<slug(title)>.md` (suffix on collision) with the title as
    an H1 heading — which `discover` reads back as the document title. Pages
    whose extracted body has fewer than `min_words` words are skipped as
    stubs and reported, not written.
    """
    report = ImportReport()
    out_dir.mkdir(parents=True, exist_ok=True)
    seen_slugs: set[str] = set()

    pages = sorted(
        p
        for p in export_dir.rglob("*.html")
        if not any(part in _SKIP_DIRS for part in p.parts)
    )
    for page in pages:
        try:
            title, body = convert_page(page.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            report.skipped_files.append(f"{page.name}: unparseable")
            continue
        if not title:
            title = page.stem
        if len(body.split()) < min_words:
            report.skipped_stubs += 1
            report.skipped_files.append(f"{page.name}: stub ({title!r})")
            continue

        slug = slugify(title) or slugify(page.stem) or "page"
        candidate, n = slug, 2
        while candidate in seen_slugs:
            candidate = f"{slug}-{n}"
            n += 1
        seen_slugs.add(candidate)

        out_path = out_dir / f"{candidate}.md"
        out_path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
        report.out_files.append(out_path)
        report.converted += 1
    return report
