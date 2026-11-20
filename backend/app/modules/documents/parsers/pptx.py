"""Reads a PowerPoint (.pptx) file slide by slide: the title, the text in reading order (top to
bottom, left to right), tables as Markdown, a short summary of each chart's data, the speaker
notes (often the best content in a deck), and the pictures when something will describe them.

Pictures that repeat across slides (a logo on a template) or are tiny or strips are ignored."""

import hashlib
import io
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from app.modules.documents.parsers.images import (
    looks_decorative,
    repeated_threshold,
    to_png,
)
from app.modules.documents.reading import (
    DocumentReadError,
    ParsedDocument,
    ParsedUnit,
    PendingImage,
    ReaderConfig,
    SkippedAsset,
    placeholder,
    table_to_markdown,
)

_CHART_POINTS = 12  # how many data points of a chart are written out


@dataclass
class _Item:
    kind: str  # "text" | "picture"
    text: str = ""
    blob: bytes = b""
    digest: str = ""


@dataclass
class _Slide:
    number: int
    title: str | None
    items: list[_Item] = field(default_factory=list)
    notes: str = ""


def read_pptx(data: bytes, cfg: ReaderConfig) -> ParsedDocument:
    try:
        presentation = Presentation(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 - python-pptx raises several types for a bad file
        raise DocumentReadError("This PowerPoint file is damaged and could not be opened.") from exc

    total = len(presentation.slides)
    if total == 0:
        raise DocumentReadError("This presentation has no slides.")
    if total > cfg.max_pages:
        raise DocumentReadError(
            f"This presentation has {total} slides and the limit is {cfg.max_pages}. Split it "
            "into smaller files and upload them separately."
        )

    slides = [_read_slide(slide, number) for number, slide in enumerate(presentation.slides, 1)]
    appears_on: Counter[str] = Counter()
    for slide in slides:
        appears_on.update({i.digest for i in slide.items if i.kind == "picture"})
    repeated = {d for d, n in appears_on.items() if n >= repeated_threshold(total) and total >= 2}

    result = ParsedDocument(units=[], page_count=total)
    decorative = 0
    for slide in slides:
        locator = f"Slide {slide.number}"
        parts: list[str] = []
        for index, item in enumerate(slide.items):
            if item.kind == "text":
                parts.append(item.text)
                continue
            if item.digest in repeated:
                decorative += 1
                continue
            png = to_png(item.blob, cfg.max_render_px)
            if png is None:
                if cfg.collect_images:
                    result.skipped.append(
                        SkippedAsset(
                            "image", locator, "not described: picture format not supported"
                        )
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
                        "image", locator, "not described: image limit reached", width, height
                    )
                )
                continue
            key = f"s{slide.number}_i{index}"
            before = "\n\n".join(parts)[-300:].strip()
            result.images.append(
                PendingImage(key, "image", data_png, width, height, locator, before or None)
            )
            parts.append(placeholder(key))
        if slide.notes:
            parts.append(f"Speaker notes: {slide.notes}")
        text = "\n\n".join(p for p in parts if p).strip()
        if text:
            result.units.append(ParsedUnit(slide.number, locator, text, slide.title))
    if decorative:
        result.notes.append(f"{decorative} decorative pictures (logos, icons) ignored.")
    return result


def _read_slide(slide: Any, number: int) -> _Slide:
    title = None
    try:
        if slide.shapes.title is not None:
            title = " ".join(slide.shapes.title.text_frame.text.split()) or None
    except Exception:  # noqa: BLE001
        title = None
    out = _Slide(number, title)
    _walk(slide.shapes, out)
    try:
        if slide.has_notes_slide:
            out.notes = slide.notes_slide.notes_text_frame.text.strip()
    except Exception:  # noqa: BLE001 - a slide without readable notes simply has none
        out.notes = ""
    return out


def _position(shape: Any) -> tuple[int, int]:
    try:
        return (int(shape.top or 0), int(shape.left or 0))
    except Exception:  # noqa: BLE001
        return (0, 0)


def _walk(shapes: Any, out: _Slide) -> None:
    for shape in sorted(shapes, key=_position):
        try:
            kind = shape.shape_type
        except NotImplementedError:
            kind = None
        if kind == MSO_SHAPE_TYPE.GROUP:
            _walk(shape.shapes, out)
            continue
        if getattr(shape, "has_table", False) and shape.has_table:
            rows = [[cell.text for cell in row.cells] for row in shape.table.rows]
            markdown = table_to_markdown(rows)
            if markdown:
                out.items.append(_Item("text", text=markdown))
            continue
        if getattr(shape, "has_chart", False) and shape.has_chart:
            summary = _chart_summary(shape.chart)
            if summary:
                out.items.append(_Item("text", text=summary))
            continue
        if kind in (MSO_SHAPE_TYPE.PICTURE, MSO_SHAPE_TYPE.PLACEHOLDER) and hasattr(shape, "image"):
            try:
                blob = shape.image.blob
            except Exception:  # noqa: BLE001 - a placeholder with no picture in it
                blob = b""
            if blob:
                out.items.append(_Item("picture", blob=blob, digest=hashlib.sha1(blob).hexdigest()))
                continue
        if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
            lines = []
            for paragraph in shape.text_frame.paragraphs:
                text = paragraph.text.strip()
                if text:
                    lines.append("  " * min(paragraph.level, 3) + text)
            if lines:
                out.items.append(_Item("text", text="\n".join(lines)))


def _chart_summary(chart: Any) -> str:
    try:
        lines = []
        if chart.has_title and chart.chart_title.has_text_frame:
            title = chart.chart_title.text_frame.text.strip()
            if title:
                lines.append(f"Chart: {title}")
        for plot in chart.plots:
            categories = [str(c) for c in plot.categories][:_CHART_POINTS]
            if categories:
                lines.append("Categories: " + ", ".join(categories))
            for series in plot.series:
                values = [f"{v:g}" if isinstance(v, float) else str(v) for v in series.values]
                lines.append(f"Series {series.name}: " + ", ".join(values[:_CHART_POINTS]))
        return "\n".join(lines)
    except Exception:  # noqa: BLE001 - an unreadable chart is skipped, never fatal
        return ""
