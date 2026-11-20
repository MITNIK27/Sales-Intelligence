"""What the readers produce, and the errors they raise.

A reader turns one uploaded file into `ParsedUnit`s (a page, a slide, a section: its text in reading
order) and `PendingImage`s (pictures and unreadable tables worth describing). Readers never call a
model: describing images is a later, optional step, and chunking is another.

Images appear inside a unit's text as a placeholder (`[[IMG:<key>]]`) until that step has run; the
pipeline then swaps each for `[IMAGE: <description>]` or removes it."""

import re
from dataclasses import dataclass, field
from typing import Literal

AssetKind = Literal["image", "table", "scanned_page"]

_PLACEHOLDER = re.compile(r"\[\[IMG:([A-Za-z0-9_]+)\]\]")


def placeholder(key: str) -> str:
    return f"[[IMG:{key}]]"


def placeholder_keys(text: str) -> list[str]:
    return _PLACEHOLDER.findall(text)


def fill_placeholders(text: str, replacements: dict[str, str]) -> str:
    """Swap each placeholder for its text (or nothing when the key has none), then tidy the gaps."""
    filled = _PLACEHOLDER.sub(lambda m: replacements.get(m.group(1), ""), text)
    return re.sub(r"\n{3,}", "\n\n", filled).strip()


class DocumentReadError(Exception):
    """A file that cannot be read, with a message written for the person who uploaded it."""


@dataclass(frozen=True)
class ReaderConfig:
    """What a reader may do. Images are only collected (rendered to PNG) when something will
    describe them, so a text-only run never pays for that."""

    max_pages: int = 300
    collect_images: bool = False
    max_images: int = 40
    min_px: int = 50
    max_banner_ratio: float = 5.0
    max_render_px: int = 1600


@dataclass
class PendingImage:
    key: str
    kind: AssetKind
    png: bytes
    width: int
    height: int
    locator: str
    # The text just before it on the page, so a description can say what it illustrates.
    context: str | None = None


@dataclass
class SkippedAsset:
    """Something that deserved a description but was left out (over the cap, unreadable format)."""

    kind: AssetKind
    locator: str
    note: str
    width: int | None = None
    height: int | None = None


@dataclass
class ParsedUnit:
    position: int  # 1-based order in the file
    locator: str  # "Page 4", "Slide 7", a section's heading
    text: str
    heading_path: str | None = None


@dataclass
class ParsedDocument:
    units: list[ParsedUnit]
    images: list[PendingImage] = field(default_factory=list)
    skipped: list[SkippedAsset] = field(default_factory=list)
    page_count: int = 0
    # Things worth telling the uploader, e.g. "12 repeated logos were ignored".
    notes: list[str] = field(default_factory=list)


def table_to_markdown(rows: list[list[str]]) -> str | None:
    """A grid of cells as a Markdown table, the first row being the header. None when it is not a
    real table (fewer than two rows or columns, or nearly empty)."""
    cleaned = [[" ".join((cell or "").split()) for cell in row] for row in rows]
    cleaned = [row for row in cleaned if any(row)]
    if len(cleaned) < 2:
        return None
    width = max(len(row) for row in cleaned)
    if width < 2:
        return None
    padded = [row + [""] * (width - len(row)) for row in cleaned]
    filled = sum(1 for row in padded for cell in row if cell)
    if filled < 0.3 * len(padded) * width:
        return None

    def line(cells: list[str]) -> str:
        return "| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |"

    out = [line(padded[0]), "|" + "|".join(" --- " for _ in range(width)) + "|"]
    out.extend(line(row) for row in padded[1:])
    return "\n".join(out)
