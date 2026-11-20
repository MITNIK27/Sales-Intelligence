"""Work out what an uploaded file really is, from its bytes: never trust the name alone, and refuse
a zip that would unpack to something huge before any library opens it."""

import io
import zipfile

from app.modules.documents.models import MEDIA_DOCX, MEDIA_MD, MEDIA_PDF, MEDIA_PPTX, MEDIA_TXT
from app.modules.documents.reading import DocumentReadError

_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # the old binary .doc / .ppt / .xls format
_MARKDOWN_EXTENSIONS = (".md", ".markdown")
_TEXT_EXTENSIONS = (".txt", ".text")
# A ratio this large on an entry of any size is how zip bombs are made.
_MAX_COMPRESSION_RATIO = 200


def _check_zip(data: bytes, max_unpacked_bytes: int) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise DocumentReadError("This file is damaged and could not be opened.") from exc
    infos = archive.infolist()
    if sum(info.file_size for info in infos) > max_unpacked_bytes:
        raise DocumentReadError(
            "This file unpacks to far more data than a normal document, so it was not opened."
        )
    for info in infos:
        if info.compress_size and info.file_size / info.compress_size > _MAX_COMPRESSION_RATIO:
            if info.file_size > 1_000_000:
                raise DocumentReadError(
                    "This file contains data that is compressed suspiciously hard, so it was not "
                    "opened."
                )
    return archive


def detect_media_type(data: bytes, filename: str, max_unpacked_bytes: int) -> str:
    """One of MEDIA_TYPES, or a `DocumentReadError` saying what is wrong."""
    if not data:
        raise DocumentReadError("This file is empty.")
    lower = filename.lower()

    if b"%PDF-" in data[:1024]:
        return MEDIA_PDF

    if data.startswith(b"PK\x03\x04"):
        names = set(_check_zip(data, max_unpacked_bytes).namelist())
        if "ppt/presentation.xml" in names:
            return MEDIA_PPTX
        if "word/document.xml" in names:
            return MEDIA_DOCX
        if "xl/workbook.xml" in names:
            raise DocumentReadError(
                "Spreadsheets are not supported yet. Export the sheet as a PDF or save the "
                "important cells in a Word document."
            )
        raise DocumentReadError("This zip file is not a PowerPoint or Word document.")

    if data.startswith(_OLE_MAGIC):
        raise DocumentReadError(
            "This is an old Office format (.doc, .ppt or .xls). Open it and save it as "
            ".docx or .pptx, or as a PDF."
        )

    if lower.endswith(_MARKDOWN_EXTENSIONS + _TEXT_EXTENSIONS):
        if b"\x00" in data[:8192]:
            raise DocumentReadError("This file looks binary, not text.")
        return MEDIA_MD if lower.endswith(_MARKDOWN_EXTENSIONS) else MEDIA_TXT

    raise DocumentReadError(
        "This type of file is not supported. Upload a PDF, PowerPoint (.pptx), Word (.docx), "
        "Markdown (.md) or text (.txt) file."
    )
