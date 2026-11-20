"""Reads a PDF with PyMuPDF: text in reading order, tables as Markdown, and (when something will
describe them) the pictures and scanned pages.

Our own pipeline for this app, in the spirit of what makes extraction trustworthy:
- reading order, including two-column pages, rather than the order the file stores text in;
- tables rebuilt as Markdown so a price list stays a price list;
- repeating headers, footers and page numbers dropped, so they do not drown the content;
- decorative pictures ignored (logos repeated on most pages, icons, banner strips);
- a page with no text of its own (a scan) is rendered whole, so it can still be read.

PyMuPDF keeps table-finding state in module globals, so two threads parsing at once can corrupt
each other's tables without any error. The whole read therefore runs under one lock.

PyMuPDF is AGPL-3.0 or a paid Artifex licence; the licence is assumed cleared (ADR 0015)."""

import math
import re
import statistics
import threading
from collections import Counter
from dataclasses import dataclass
from typing import Any

import pymupdf

from app.modules.documents.parsers.images import looks_decorative, repeated_threshold
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

# PyMuPDF advertises its optional layout add-on on stdout; this is its own switch for that.
pymupdf.no_recommend_layout()

_LOCK = threading.RLock()

_BULLET = re.compile(r"^\s*(?:[•▪◦●‣▶►■□–—*-]|\d{1,2}[.)])\s+")
_ENDS_SENTENCE = re.compile(r"[.!?:][\"'”’)\]]?$")
_STARTS_NEW = re.compile(r"^[A-Z0-9“\"'(\[]")
_ENDS_WITH_URL = re.compile(r"https?://\S+$")
# A line that stops this share of the text width short of the margin has ended an item or paragraph.
_SHORT_LINE = 0.15
# ... or this much, when it also ends a sentence and the next line starts a new one.
_SENTENCE_GAP = 0.05
_PARAGRAPH_GAP = 0.45  # a gap above a line, as a share of its height, starts a new paragraph
_INDENT_STEP = 12.0  # points; a line indented or outdented by more is a new item
_HEADING_RATIO = 1.35  # type this much larger than the body is a heading ...
_TITLE_RATIO = 2.5  # ... and this much larger a top-level one
_HEADING_CHARS = 150
_MARGIN = 0.07  # the top and bottom 7% of a page (about 0.8 inch) hold headers and footers
_MIN_PAGE_TEXT = 20  # fewer characters than this and a page counts as having no text of its own
_CONTEXT_CHARS = 300
_WIDE = 0.6  # a block wider than this share of the page spans the columns


@dataclass
class _Block:
    kind: str  # "text" | "table" | "image"
    x0: float
    y0: float
    x1: float
    y1: float
    text: str = ""
    size: float = 0.0
    level: int = 0  # 1 or 2 when the type is large enough to be a heading
    key: str = ""  # image placeholder key


def read_pdf(data: bytes, cfg: ReaderConfig) -> ParsedDocument:
    with _LOCK:
        return _read_pdf(data, cfg)


def _read_pdf(data: bytes, cfg: ReaderConfig) -> ParsedDocument:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 - PyMuPDF raises several types for a bad file
        raise DocumentReadError("This PDF is damaged and could not be opened.") from exc
    with doc:
        if doc.needs_pass or doc.is_encrypted:
            raise DocumentReadError(
                "This PDF is password protected. Remove the password and upload it again."
            )
        total = doc.page_count
        if total == 0:
            raise DocumentReadError("This PDF has no pages.")
        if total > cfg.max_pages:
            raise DocumentReadError(
                f"This PDF has {total} pages and the limit is {cfg.max_pages}. Split it into "
                "smaller files and upload them separately."
            )

        scans = [_scan_page(doc[i], i + 1, cfg) for i in range(total)]
        repeated = _repeated_margin_keys(scans, total)
        repeated_xrefs = _repeated_xrefs(scans, total)
        body_size = _body_font_size(scans)

        result = ParsedDocument(units=[], page_count=total)
        counter = {"decor": 0, "scans": 0, "images": 0}
        for scan in scans:
            unit = _assemble(
                doc[scan.number - 1],
                scan,
                repeated,
                repeated_xrefs,
                body_size,
                cfg,
                result,
                counter,
            )
            if unit is not None:
                result.units.append(unit)
        if counter["decor"]:
            result.notes.append(f"{counter['decor']} decorative pictures (logos, icons) ignored.")
        if counter["scans"]:
            result.notes.append(f"{counter['scans']} page(s) had no text of their own (scans).")
        return result


@dataclass
class _Scan:
    number: int
    width: float
    height: float
    blocks: list[_Block]
    image_candidates: list[tuple[int, pymupdf.Rect, int, int]]  # (xref, rect, px_w, px_h)
    unparsed_tables: list[pymupdf.Rect]
    has_drawings: bool


def _scan_page(page: pymupdf.Page, number: int, cfg: ReaderConfig) -> _Scan:
    rect = page.rect
    tables: list[tuple[pymupdf.Rect, str | None]] = []
    try:
        for table in page.find_tables().tables:
            tables.append((pymupdf.Rect(table.bbox), table_to_markdown(table.extract())))
    except Exception:  # noqa: BLE001 - table finding is best effort; the text is still read
        tables = []

    blocks: list[_Block] = []
    for raw in page.get_text("dict")["blocks"]:
        if raw.get("type") != 0:
            continue
        text, size = _block_text(raw)
        if not text:
            continue
        x0, y0, x1, y1 = raw["bbox"]
        block = _Block("text", x0, y0, x1, y1, text=text, size=size)
        if any(md and _inside(block, area) for area, md in tables):
            continue  # its words are in the table below
        blocks.append(block)
    for area, md in tables:
        if md:
            blocks.append(_Block("table", area.x0, area.y0, area.x1, area.y1, text=md))

    candidates: list[tuple[int, pymupdf.Rect, int, int]] = []
    try:
        for item in page.get_images(full=True):
            xref, px_w, px_h = item[0], item[2], item[3]
            rects = page.get_image_rects(xref)
            if rects:
                candidates.append((xref, rects[0], px_w, px_h))
    except Exception:  # noqa: BLE001
        candidates = []
    unparsed = [area for area, md in tables if not md and area.width > 60 and area.height > 40]
    try:
        has_drawings = len(page.get_drawings()) > 0
    except Exception:  # noqa: BLE001
        has_drawings = False
    return _Scan(number, rect.width, rect.height, blocks, candidates, unparsed, has_drawings)


@dataclass
class _Line:
    text: str
    x0: float
    x1: float
    y0: float
    y1: float


def _block_text(raw: dict[str, Any]) -> tuple[str, float]:
    lines: list[_Line] = []
    weighted = 0.0
    chars = 0
    for line in raw.get("lines", []):
        text = "".join(span["text"] for span in line.get("spans", [])).strip()
        if not text:
            continue
        x0, y0, x1, y1 = line["bbox"]
        lines.append(_Line(text, x0, x1, y0, y1))
        for span in line["spans"]:
            weighted += span["size"] * len(span["text"])
            chars += len(span["text"])
    if not lines:
        return "", 0.0
    return _join_lines(lines), (weighted / chars if chars else 0.0)


def _join_lines(lines: list[_Line]) -> str:
    """Rebuilds paragraphs and list items from the lines of one text block. Many PDFs store a whole
    section as one block with no bullet characters and no gaps, so the only sign that an item ended
    is that its last line stops short of the right margin. Wrapped lines run to the margin."""
    rights = sorted(line.x1 for line in lines)
    right = rights[-1] if len(rights) < 4 else rights[int(0.9 * (len(rights) - 1))]
    left = min(line.x0 for line in lines)
    span = max(right - left, 1.0)
    out = lines[0].text
    for previous, line in zip(lines, lines[1:], strict=False):
        out += _glue(previous, line, right, span) + line.text
    return out.strip()


def _glue(previous: _Line, line: _Line, right: float, span: float) -> str:
    if _BULLET.match(line.text):
        return "\n"
    height = max(previous.y1 - previous.y0, 1.0)
    if line.y0 - previous.y1 > _PARAGRAPH_GAP * height:
        return "\n\n"
    if abs(line.x0 - previous.x0) > _INDENT_STEP:
        return "\n"
    short_by = right - previous.x1
    if short_by > _SHORT_LINE * span or _ENDS_WITH_URL.search(previous.text):
        return "\n"
    if (
        short_by > _SENTENCE_GAP * span
        and _ENDS_SENTENCE.search(previous.text)
        and _STARTS_NEW.match(line.text)
    ):
        return "\n"
    return " "


def _inside(block: _Block, area: pymupdf.Rect) -> bool:
    own = pymupdf.Rect(block.x0, block.y0, block.x1, block.y1)
    if own.is_empty:
        return False
    overlap = own & area
    return not overlap.is_empty and overlap.get_area() / own.get_area() >= 0.6


def _margin_key(text: str) -> str:
    return re.sub(r"\d+", "#", " ".join(text.lower().split()))


def _in_margin(block: _Block, height: float) -> bool:
    return block.y1 <= height * _MARGIN or block.y0 >= height * (1 - _MARGIN)


def _repeated_margin_keys(scans: list[_Scan], total: int) -> set[str]:
    """Header and footer lines that repeat on at least half the pages (page numbers included, as
    digits are folded together). Not attempted on a one- or two-page file."""
    if total < 3:
        return set()
    seen: Counter[str] = Counter()
    for scan in scans:
        keys = {
            _margin_key(b.text)
            for b in scan.blocks
            if b.kind == "text" and _in_margin(b, scan.height)
        }
        seen.update(keys)
    need = max(2, math.ceil(total * 0.5))
    return {key for key, count in seen.items() if count >= need}


def _repeated_xrefs(scans: list[_Scan], total: int) -> set[int]:
    seen: Counter[int] = Counter()
    for scan in scans:
        seen.update({xref for xref, *_ in scan.image_candidates})
    need = repeated_threshold(total)
    return {xref for xref, count in seen.items() if count >= need and total >= 2}


def _body_font_size(scans: list[_Scan]) -> float:
    sizes: list[float] = []
    for scan in scans:
        for block in scan.blocks:
            if block.kind == "text" and block.size:
                sizes.extend([block.size] * max(1, len(block.text) // 20))
    return statistics.median(sizes) if sizes else 0.0


def _two_columns(blocks: list[_Block], width: float, height: float) -> bool:
    narrow = [b for b in blocks if (b.x1 - b.x0) <= _WIDE * width]
    left = [b for b in narrow if (b.x0 + b.x1) / 2 < width / 2]
    right = [b for b in narrow if (b.x0 + b.x1) / 2 >= width / 2]
    if len(left) < 3 or len(right) < 3:
        return False
    reach = min(max(b.y1 for b in side) - min(b.y0 for b in side) for side in (left, right))
    return reach >= 0.25 * height


def _reading_order(blocks: list[_Block], width: float, height: float) -> list[_Block]:
    ordered = sorted(blocks, key=lambda b: (b.y0, b.x0))
    if not _two_columns(blocks, width, height):
        return ordered
    out: list[_Block] = []
    left: list[_Block] = []
    right: list[_Block] = []

    def flush() -> None:
        out.extend(sorted(left, key=lambda b: b.y0))
        out.extend(sorted(right, key=lambda b: b.y0))
        left.clear()
        right.clear()

    for block in ordered:
        if (block.x1 - block.x0) > _WIDE * width:
            flush()
            out.append(block)
        elif (block.x0 + block.x1) / 2 < width / 2:
            left.append(block)
        else:
            right.append(block)
    flush()
    return out


def _render(page: pymupdf.Page, area: pymupdf.Rect, cfg: ReaderConfig) -> tuple[bytes, int, int]:
    longest = max(area.width, area.height, 1.0)
    dpi = int(min(150, max(72, cfg.max_render_px / (longest / 72))))
    pixmap = page.get_pixmap(clip=area, dpi=dpi)
    return pixmap.tobytes("png"), pixmap.width, pixmap.height


def _assemble(
    page: pymupdf.Page,
    scan: _Scan,
    repeated_margins: set[str],
    repeated_xrefs: set[int],
    body_size: float,
    cfg: ReaderConfig,
    result: ParsedDocument,
    counter: dict[str, int],
) -> ParsedUnit | None:
    locator = f"Page {scan.number}"
    blocks = [
        b
        for b in scan.blocks
        if not (
            b.kind == "text"
            and _in_margin(b, scan.height)
            and _margin_key(b.text) in repeated_margins
        )
    ]
    text_chars = sum(len(b.text) for b in blocks if b.kind == "text")
    for block in blocks:
        if block.kind == "text":
            block.level = _heading_level(block, body_size)

    # A page with no words of its own: a scan, or a slide that is one big picture.
    if text_chars < _MIN_PAGE_TEXT and (scan.image_candidates or scan.has_drawings):
        counter["scans"] += 1
        key = f"p{scan.number}_scan"
        if cfg.collect_images and len(result.images) < cfg.max_images:
            png, w, h = _render(page, page.rect, cfg)
            result.images.append(PendingImage(key, "scanned_page", png, w, h, locator))
            return ParsedUnit(scan.number, locator, placeholder(key))
        result.skipped.append(
            SkippedAsset(
                "scanned_page",
                locator,
                "not described: image descriptions are off or the limit was reached",
            )
        )
        return None

    page_area = scan.width * scan.height
    for index, (xref, area, px_w, px_h) in enumerate(scan.image_candidates):
        if looks_decorative(px_w, px_h, cfg) or xref in repeated_xrefs:
            counter["decor"] += 1
            continue
        if area.width < 24 or area.height < 24 or area.get_area() < 0.005 * page_area:
            counter["decor"] += 1
            continue
        if area.get_area() >= 0.9 * page_area:
            counter["decor"] += 1  # a full-page background behind real text
            continue
        key = f"p{scan.number}_i{index}"
        if not cfg.collect_images:
            continue
        if len(result.images) >= cfg.max_images:
            result.skipped.append(
                SkippedAsset("image", locator, "not described: image limit reached", px_w, px_h)
            )
            continue
        png, w, h = _render(page, area, cfg)
        result.images.append(PendingImage(key, "image", png, w, h, locator))
        blocks.append(_Block("image", area.x0, area.y0, area.x1, area.y1, key=key))
    if cfg.collect_images:
        for index, area in enumerate(scan.unparsed_tables):
            key = f"p{scan.number}_t{index}"
            if len(result.images) >= cfg.max_images:
                result.skipped.append(
                    SkippedAsset("table", locator, "not described: image limit reached")
                )
                continue
            png, w, h = _render(page, area, cfg)
            result.images.append(PendingImage(key, "table", png, w, h, locator))
            blocks.append(_Block("image", area.x0, area.y0, area.x1, area.y1, key=key))

    if not blocks:
        return None
    heading = _page_heading(blocks, body_size)
    text = _join(_reading_order(blocks, scan.width, scan.height), result.images)
    if not text:
        return None
    return ParsedUnit(scan.number, locator, text, heading)


def _heading_level(block: _Block, body_size: float) -> int:
    """1 or 2 for a short run of text set in clearly larger type than the body, else 0."""
    if not body_size or len(block.text) > _HEADING_CHARS or block.text.count("\n") > 1:
        return 0
    if block.size >= body_size * _TITLE_RATIO:
        return 1
    return 2 if block.size >= body_size * _HEADING_RATIO else 0


def _page_heading(blocks: list[_Block], body_size: float) -> str | None:
    if not body_size:
        return None
    titles = [
        b
        for b in blocks
        if b.kind == "text"
        and b.size >= max(body_size * 1.25, body_size + 2)
        and len(b.text) <= 150
    ]
    if not titles:
        return None
    best = max(titles, key=lambda b: (round(b.size), -b.y0))
    return " ".join(best.text.split())


def _join(ordered: list[_Block], images: list[PendingImage]) -> str:
    by_key: dict[str, PendingImage] = {image.key: image for image in images}
    out = ""
    previous_short = False
    for block in ordered:
        if block.kind == "image":
            image = by_key.get(block.key)
            if image is not None:
                image.context = out[-_CONTEXT_CHARS:].strip() or None
            piece, short = placeholder(block.key), False
        else:
            piece = f"{'#' * block.level} {block.text}" if block.level else block.text
            short = (
                block.kind == "text"
                and not block.level
                and "\n" not in block.text
                and len(block.text) < 80
            )
        glue = "\n" if (short and previous_short) else "\n\n"
        out += (glue if out else "") + piece
        previous_short = short
    return out.strip()
