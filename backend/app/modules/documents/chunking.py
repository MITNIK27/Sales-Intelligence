"""Cuts each page, slide or section into the passages search will find.

- A unit that fits (up to `max_whole` characters) stays whole: a slide is one idea.
- A longer one is cut at paragraph and sentence edges into chunks of about `target` characters,
  never in the middle of a sentence where it can be avoided.
- When a unit is split, the next chunk starts with the last sentence or two of the previous one
  (up to `overlap` characters), so a thought cut at the boundary is found from either side.
- A Markdown table that has to be split is split by rows, with the header row repeated on each
  part, so every part still says which column is which.
- Every chunk keeps its unit's locator and heading path, for citation."""

import re
from dataclasses import dataclass

from app.modules.documents.reading import ParsedUnit

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")
_MIN_SMALL = 200  # a chunk shorter than this is folded into a neighbour when the two fit together


@dataclass(frozen=True)
class ChunkConfig:
    target: int = 1000
    max_whole: int = 1400
    overlap: int = 150


@dataclass(frozen=True)
class ChunkDraft:
    ordinal: int
    locator: str
    heading_path: str | None
    text: str


def chunk_units(units: list[ParsedUnit], cfg: ChunkConfig) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for unit in units:
        for text in chunk_text(unit.text, cfg):
            drafts.append(ChunkDraft(len(drafts) + 1, unit.locator, unit.heading_path, text))
    return drafts


def chunk_text(text: str, cfg: ChunkConfig) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= cfg.max_whole:
        return [text]

    pieces = _pieces(text, cfg.target)
    chunks = _merge_small(_pack(pieces, cfg.target), cfg.max_whole)
    return _with_overlap(chunks, cfg.overlap)


def _merge_small(chunks: list[str], max_whole: int) -> list[str]:
    """Fold a very short chunk into the one after it (or, for the last, the one before) when the
    two still fit together, so no chunk is a stray line."""
    out: list[str] = []
    for index, chunk in enumerate(chunks):
        fits = bool(out) and len(out[-1]) + 2 + len(chunk) <= max_whole
        last_is_stray = index == len(chunks) - 1 and len(chunk) < _MIN_SMALL
        if fits and (len(out[-1]) < _MIN_SMALL or last_is_stray):
            out[-1] = out[-1] + "\n\n" + chunk
        else:
            out.append(chunk)
    return out


def _is_table(block: str) -> bool:
    lines = [line for line in block.split("\n") if line.strip()]
    return len(lines) >= 2 and all(line.lstrip().startswith("|") for line in lines)


def _sentences(text: str, limit: int) -> list[str]:
    out: list[str] = []
    for sentence in _SENTENCE_END.split(text):
        sentence = sentence.strip()
        while len(sentence) > limit:
            cut = sentence.rfind(" ", 0, limit)
            cut = cut if cut > limit // 2 else limit
            out.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if sentence:
            out.append(sentence)
    return out


def _table_parts(block: str, limit: int) -> list[str]:
    lines = [line for line in block.split("\n") if line.strip()]
    header, rows = lines[:2], lines[2:]
    parts: list[str] = []
    current: list[str] = []
    size = len("\n".join(header))
    for row in rows:
        if current and size + len(row) + 1 > limit:
            parts.append("\n".join(header + current))
            current, size = [], len("\n".join(header))
        current.append(row)
        size += len(row) + 1
    if current:
        parts.append("\n".join(header + current))
    return parts or ["\n".join(header)]


def _pieces(text: str, limit: int) -> list[tuple[str, bool]]:
    """(text, starts_a_new_paragraph) pieces, each at most `limit` long (a table part may run a
    little over when one row is itself longer than that)."""
    out: list[tuple[str, bool]] = []
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        if _is_table(block):
            parts = [block] if len(block) <= limit else _table_parts(block, limit)
            out.extend((part, True) for part in parts)
            continue
        first = True
        for line in block.split("\n"):
            line = line.strip()
            if not line:
                continue
            atoms = [line] if len(line) <= limit else _sentences(line, limit)
            for atom in atoms:
                out.append((atom, first))
                first = False
    return out


def _pack(pieces: list[tuple[str, bool]], limit: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for text, new_paragraph in pieces:
        glue = "\n\n" if new_paragraph else "\n"
        if current and len(current) + len(glue) + len(text) > limit:
            chunks.append(current)
            current = text
        else:
            current = current + glue + text if current else text
    if current:
        chunks.append(current)
    return chunks


def _tail(text: str, limit: int) -> str:
    """The last sentence or two of `text`, up to `limit` characters; empty for a table."""
    last_block = text.split("\n\n")[-1]
    if _is_table(last_block) or last_block.lstrip().startswith("|"):
        return ""
    sentences = _sentences(last_block, limit)
    tail = ""
    for sentence in reversed(sentences):
        if len(tail) + len(sentence) + 1 > limit:
            break
        tail = sentence + (" " + tail if tail else "")
    return _whole_words(last_block, tail)


def _whole_words(source: str, tail: str) -> str:
    """A sentence that had to be cut by length (a long link has no spaces) can start in the middle
    of a word. An overlap must begin at a word edge, so drop the partial first word."""
    at = source.rfind(tail)
    if at <= 0 or source[at - 1].isspace():
        return tail
    _, _, rest = tail.partition(" ")
    return rest.strip()


def _with_overlap(chunks: list[str], overlap: int) -> list[str]:
    if overlap <= 0 or len(chunks) < 2:
        return chunks
    out = [chunks[0]]
    for previous, chunk in zip(chunks, chunks[1:], strict=False):
        tail = _tail(previous, overlap)
        out.append(f"{tail}\n\n{chunk}" if tail and tail not in chunk else chunk)
    return out
