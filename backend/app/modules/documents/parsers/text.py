"""Markdown and plain text. Markdown is split into sections at its top-level headings; plain text
is one section. Links and image references in the text are left as written: nothing is fetched."""

import codecs
import re

from app.modules.documents.parsers.sections import SectionBuilder
from app.modules.documents.reading import DocumentReadError, ParsedDocument, ParsedUnit

_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t#]*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


def decode(data: bytes) -> str:
    if data.startswith(codecs.BOM_UTF8):
        return data.decode("utf-8-sig")
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")  # an old Windows text file


def read_text(data: bytes) -> ParsedDocument:
    text = decode(data).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise DocumentReadError("This file has no text in it.")
    return ParsedDocument(units=[ParsedUnit(1, "Text", text)], page_count=1)


def read_markdown(data: bytes) -> ParsedDocument:
    text = decode(data).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise DocumentReadError("This file has no text in it.")

    items: list[tuple[int, str]] = []  # (heading level, text) or (0, paragraph block)
    block: list[str] = []
    in_fence = False

    def flush_block() -> None:
        joined = "\n".join(block).strip()
        if joined:
            items.append((0, joined))
        block.clear()

    for line in text.split("\n"):
        if _FENCE.match(line):
            in_fence = not in_fence
            block.append(line)
            continue
        match = None if in_fence else _HEADING.match(line)
        if match:
            flush_block()
            items.append((len(match.group(1)), match.group(2)))
        elif not line.strip() and not in_fence:
            flush_block()
        else:
            block.append(line)
    flush_block()

    levels = [level for level, _ in items if level]
    builder = SectionBuilder(min(levels) if levels else None)
    for level, value in items:
        if level:
            builder.heading(level, value)
        else:
            builder.add(value)
    units = builder.units()
    return ParsedDocument(units=units, page_count=len(units))
