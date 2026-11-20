"""Reads a Word (.docx) file: headings give the structure (each top-level heading is a section that
can be cited), paragraphs and lists keep their order, tables become Markdown, and pictures inside
the text are collected when something will describe them."""

import hashlib
import io
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.modules.documents.parsers.images import looks_decorative, to_png
from app.modules.documents.parsers.sections import SectionBuilder
from app.modules.documents.reading import (
    DocumentReadError,
    ParsedDocument,
    PendingImage,
    ReaderConfig,
    SkippedAsset,
    placeholder,
    table_to_markdown,
)

_HEADING_STYLE = re.compile(r"^Heading\s+(\d)$", re.IGNORECASE)
_BLIP = ".//a:blip/@r:embed"
_REPEATED_PICTURE = 3  # the same picture this many times is a bullet icon or a divider


@dataclass
class _Item:
    kind: str  # "heading" | "text" | "table" | "image"
    level: int = 0
    text: str = ""
    blob: bytes = b""
    digest: str = ""  # fingerprint of a picture, to recognise one used again and again


def read_docx(data: bytes, cfg: ReaderConfig) -> ParsedDocument:
    try:
        document = Document(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 - python-docx raises several types for a bad file
        raise DocumentReadError("This Word file is damaged and could not be opened.") from exc

    items = _collect(document)
    title = next((i.text for i in items if i.kind == "heading" and i.level == 0), None)
    levels = [i.level for i in items if i.kind == "heading" and i.level > 0]
    builder = SectionBuilder(min(levels) if levels else None, title)

    result = ParsedDocument(units=[])
    uses = Counter(item.digest for item in items if item.kind == "image")
    decorative = 0
    for index, item in enumerate(items):
        if item.kind == "heading":
            if item.level > 0:
                builder.heading(item.level, item.text)
            continue
        if item.kind != "image":
            builder.add(item.text)
            continue
        if uses[item.digest] >= _REPEATED_PICTURE:
            decorative += 1
            continue
        png = to_png(item.blob, cfg.max_render_px)
        if png is None:
            if cfg.collect_images:
                result.skipped.append(
                    SkippedAsset("image", "Document", "not described: picture format not supported")
                )
            continue
        data_png, width, height = png
        if looks_decorative(width, height, cfg):
            decorative += 1
            continue
        if not cfg.collect_images:
            continue
        if len(result.images) >= cfg.max_images:
            result.skipped.append(
                SkippedAsset(
                    "image", "Document", "not described: image limit reached", width, height
                )
            )
            continue
        key = f"d{index}"
        result.images.append(PendingImage(key, "image", data_png, width, height, "Document"))
        builder.add(placeholder(key))

    result.units = builder.units()
    result.page_count = len(result.units)
    if decorative:
        result.notes.append(f"{decorative} decorative pictures (icons, dividers) ignored.")
    return result


def _collect(document: Any) -> list[_Item]:
    items: list[_Item] = []
    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            _paragraph(Paragraph(child, document), document, items)
        elif tag == "tbl":
            rows = _table_rows(Table(child, document))
            markdown = table_to_markdown(rows)
            if markdown:
                items.append(_Item("table", text=markdown))
            else:
                flat = " ".join(" ".join(cell for cell in row if cell) for row in rows).strip()
                if flat:
                    items.append(_Item("text", text=flat))
    return items


def _style_name(paragraph: Paragraph) -> str:
    try:
        style = paragraph.style
        return str(style.name or "") if style is not None else ""
    except Exception:  # noqa: BLE001 - a missing style definition is not an error for us
        return ""


def _paragraph(paragraph: Paragraph, document: Any, items: list[_Item]) -> None:
    text = paragraph.text.strip()
    style = _style_name(paragraph)
    match = _HEADING_STYLE.match(style)
    if text and match:
        items.append(_Item("heading", level=int(match.group(1)), text=text))
    elif text and style.lower() == "title":
        items.append(_Item("heading", level=0, text=text))
    elif text:
        bullet = "- " if style.lower().startswith("list") else ""
        items.append(_Item("text", text=bullet + text))
    try:
        for rid in paragraph._p.xpath(_BLIP):
            part = document.part.related_parts.get(rid)
            if part is not None:
                items.append(
                    _Item("image", blob=part.blob, digest=hashlib.sha1(part.blob).hexdigest())
                )
    except Exception:  # noqa: BLE001 - an unreadable picture reference is just skipped
        return


def _table_rows(table: Table) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in table.rows:
        cells: list[str] = []
        previous = None
        for cell in row.cells:
            if cell._tc is previous:  # a merged cell is reported once per column it spans
                continue
            previous = cell._tc
            cells.append(cell.text)
        rows.append(cells)
    return rows
