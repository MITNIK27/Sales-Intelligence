"""Manual tool: check that what is stored for the documents is complete and consistent. Read-only,
never changes anything.

For every document version it checks that:
  * the counts on the version match the rows (pages, passages);
  * passages are numbered 1..n with no gap, and their stored length matches their text;
  * no passage is missing text that is on its page, and none contains words that are not (the
    passages are cut from the page text, so nothing may be lost or invented);
  * every passage has its search entry (the full-text column);
  * no placeholder from the reader (`[[IMG:...]]`) leaked into saved text;
  * every description a model wrote records which model and prompt wrote it;
  * a file is only still held when something is left to retry.

With `--file PATH` it also reads that file again with the same reader and compares it with the
stored pages of the document you name (`--document NAME`), word for word. That is the direct proof
that what is in the database is what the file says. Pictures are not described for this check, so
compare a file whose descriptions were not on.

Usage (from backend/, venv active):
    python scripts/documents_verify.py
    python scripts/documents_verify.py --document AI --file "C:\\path\\to\\AI.pdf"
"""

import argparse
import asyncio
import re
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import models as _models  # noqa: F401 - registers every table
from app.db.session import SessionLocal
from app.modules.documents.detect import detect_media_type
from app.modules.documents.models import (
    STATUS_READY,
    Document,
    DocumentAsset,
    DocumentChunk,
    DocumentPage,
    DocumentUpload,
    DocumentVersion,
)
from app.modules.documents.parsers import read_document
from app.modules.documents.service import reader_config

_WORD = re.compile(r"\S+")


def _words(text: str) -> list[str]:
    """The words of a text, ignoring the Markdown heading marks the reader adds."""
    return [w for w in _WORD.findall(text) if not re.fullmatch(r"#{1,6}", w)]


async def _check_version(session: AsyncSession, version: DocumentVersion, name: str) -> list[str]:
    problems: list[str] = []
    pages = (
        (
            await session.execute(
                select(DocumentPage)
                .where(DocumentPage.version_id == version.id)
                .order_by(DocumentPage.position)
            )
        )
        .scalars()
        .all()
    )
    chunks = (
        (
            await session.execute(
                select(DocumentChunk)
                .where(DocumentChunk.version_id == version.id)
                .order_by(DocumentChunk.ordinal)
            )
        )
        .scalars()
        .all()
    )
    if version.status != STATUS_READY:
        return problems  # nothing is expected to be saved until it has been read

    if len(chunks) != version.chunk_count:
        problems.append(f"the version says {version.chunk_count} passages, {len(chunks)} are saved")
    if [c.ordinal for c in chunks] != list(range(1, len(chunks) + 1)):
        problems.append("passage numbers are not 1..n")
    if version.page_count is not None and len(pages) > version.page_count:
        problems.append(f"{len(pages)} pages saved but the file has {version.page_count}")
    for chunk in chunks:
        if chunk.char_count != len(chunk.text):
            problems.append(f"passage {chunk.ordinal}: stored length does not match its text")

    by_locator: dict[str, list[DocumentChunk]] = defaultdict(list)
    for chunk in chunks:
        by_locator[chunk.locator].append(chunk)
    for page in pages:
        page_words = set(_words(page.text))
        chunk_words = {w for c in by_locator.get(page.locator, []) for w in _words(c.text)}
        lost = page_words - chunk_words
        invented = chunk_words - page_words
        if lost:
            problems.append(f"{page.locator}: {len(lost)} words are on the page but in no passage")
        if invented:
            problems.append(
                f"{page.locator}: passages contain {len(invented)} words not on the page"
            )
    page_locators = {p.locator for p in pages}
    for locator in set(by_locator) - page_locators:
        problems.append(f"passages exist for {locator} but there is no such page")

    leaked = sum("[[IMG:" in p.text for p in pages) + sum("[[IMG:" in c.text for c in chunks)
    if leaked:
        problems.append(f"{leaked} saved texts still contain a reader placeholder")

    without_search = await session.scalar(
        select(func.count())
        .select_from(DocumentChunk)
        .where(DocumentChunk.version_id == version.id, DocumentChunk.tsv.is_(None))
    )
    if without_search:
        problems.append(f"{without_search} passages have no search entry")

    assets = (
        (await session.execute(select(DocumentAsset).where(DocumentAsset.version_id == version.id)))
        .scalars()
        .all()
    )
    for asset in assets:
        if asset.status == "described" and not (
            asset.description and asset.model_used and asset.prompt_version
        ):
            problems.append(f"{asset.locator}: a description has no text, model or prompt recorded")

    held = await session.scalar(
        select(func.count())
        .select_from(DocumentUpload)
        .where(DocumentUpload.version_id == version.id)
    )
    if held and not any(a.status == "failed" for a in assets):
        problems.append("the uploaded file is still held although nothing is left to retry")
    print(
        f"  {name} v{version.version}: {len(pages)} pages, {len(chunks)} passages, "
        f"{len(assets)} pictures, "
        f"search entries {len(chunks) - (without_search or 0)}/{len(chunks)}"
    )
    return problems


async def _compare_with_file(session: AsyncSession, document_name: str, path: Path) -> list[str]:
    settings = get_settings()
    data = path.read_bytes()
    media = detect_media_type(data, path.name, settings.documents_max_unpacked_mb * 1024 * 1024)
    fresh = read_document(media, data, reader_config(settings, collect_images=False))

    document = (
        await session.execute(select(Document).where(Document.name == document_name))
    ).scalar_one_or_none()
    if document is None:
        return [f"no document is named {document_name!r}"]
    version = (
        await session.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document.id, DocumentVersion.is_current
            )
        )
    ).scalar_one_or_none()
    if version is None:
        return ["that document has no current version"]
    stored = {
        p.locator: p.text
        for p in (
            await session.execute(select(DocumentPage).where(DocumentPage.version_id == version.id))
        ).scalars()
    }
    problems: list[str] = []
    read = {u.locator: u.text for u in fresh.units}
    for locator in sorted(set(read) | set(stored)):
        if locator not in stored:
            problems.append(f"{locator}: in the file but not saved")
        elif locator not in read:
            problems.append(f"{locator}: saved but not in the file")
        elif _words(read[locator]) != _words(stored[locator]):
            problems.append(f"{locator}: the saved words differ from the file's")
    same = sum(1 for k in read if k in stored and _words(read[k]) == _words(stored[k]))
    print(f"  compared with {path.name}: {same} of {len(read)} pages match word for word")
    return problems


async def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, help="the original file, to compare against")
    parser.add_argument("--document", help="the name of the document that file was saved as")
    args = parser.parse_args()
    if bool(args.file) != bool(args.document):
        parser.error("--file and --document go together")

    problems: list[str] = []
    async with SessionLocal() as session:
        await session.execute(select(1))
        versions = (
            await session.execute(
                select(DocumentVersion, Document.name)
                .join(Document, Document.id == DocumentVersion.document_id)
                .order_by(Document.name, DocumentVersion.version)
            )
        ).all()
        print(f"{len(versions)} document version(s) in the database")
        for version, name in versions:
            problems += [
                f"{name} v{version.version}: {p}"
                for p in await _check_version(session, version, name)
            ]
        if args.file:
            problems += [
                f"{args.document}: {p}"
                for p in await _compare_with_file(session, args.document, args.file)
            ]
    print()
    if problems:
        print("PROBLEMS:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("OK: everything stored is complete and consistent.")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    sys.exit(asyncio.run(_main()))
