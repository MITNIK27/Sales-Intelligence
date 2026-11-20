"""One entry point for every supported file type."""

from app.modules.documents.models import MEDIA_DOCX, MEDIA_MD, MEDIA_PDF, MEDIA_PPTX, MEDIA_TXT
from app.modules.documents.parsers.docx import read_docx
from app.modules.documents.parsers.pdf import read_pdf
from app.modules.documents.parsers.pptx import read_pptx
from app.modules.documents.parsers.text import read_markdown, read_text
from app.modules.documents.reading import DocumentReadError, ParsedDocument, ReaderConfig


def read_document(media_type: str, data: bytes, cfg: ReaderConfig) -> ParsedDocument:
    """Reads `data` as `media_type` (from `detect.detect_media_type`) into pages and images.
    Raises `DocumentReadError` with a message for the uploader when the file cannot be read."""
    if media_type == MEDIA_PDF:
        return read_pdf(data, cfg)
    if media_type == MEDIA_PPTX:
        return read_pptx(data, cfg)
    if media_type == MEDIA_DOCX:
        return read_docx(data, cfg)
    if media_type == MEDIA_MD:
        return read_markdown(data)
    if media_type == MEDIA_TXT:
        return read_text(data)
    raise DocumentReadError(f"Unsupported file type: {media_type}")
