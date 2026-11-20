"""Splits a flowing document (Word, Markdown) into sections at its top-level headings, so each
section can be cited by its heading. A file with no headings is one section."""

from app.modules.documents.reading import ParsedUnit

_LOCATOR_CHARS = 80


class SectionBuilder:
    def __init__(self, split_level: int | None, title: str | None = None) -> None:
        self._split = split_level
        self._title = title
        self._stack: dict[int, str] = {}
        self._units: list[ParsedUnit] = []
        self._locator = "Introduction" if split_level is not None else "Document"
        self._path: str | None = title
        self._pieces: list[str] = []

    def heading(self, level: int, text: str) -> None:
        text = " ".join(text.split())
        if not text:
            return
        self._stack = {k: v for k, v in self._stack.items() if k < level}
        self._stack[level] = text
        if self._split is not None and level == self._split:
            self._flush()
            self._locator = text[:_LOCATOR_CHARS]
            parts = [self._title] if self._title else []
            self._path = " > ".join(parts + [self._stack[k] for k in sorted(self._stack)])
            self._pieces.append(f"# {text}")
        else:
            depth = level - (self._split or 1) + 1
            self._pieces.append(f"{'#' * max(1, depth)} {text}")

    def add(self, piece: str) -> None:
        piece = piece.strip()
        if piece:
            self._pieces.append(piece)

    def _flush(self) -> None:
        text = "\n\n".join(self._pieces).strip()
        if text:
            self._units.append(ParsedUnit(len(self._units) + 1, self._locator, text, self._path))
        self._pieces = []

    def units(self) -> list[ParsedUnit]:
        self._flush()
        return self._units
