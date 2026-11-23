import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UpdatedAtMixin, new_uuid

# What a file is, found from its content (never from its name alone).
MEDIA_PDF = "pdf"
MEDIA_PPTX = "pptx"
MEDIA_DOCX = "docx"
MEDIA_MD = "md"
MEDIA_TXT = "txt"
MEDIA_TYPES = (MEDIA_PDF, MEDIA_PPTX, MEDIA_DOCX, MEDIA_MD, MEDIA_TXT)

# A version moves queued -> processing -> ready (or failed). `ready` means its text is extracted and
# chunked; embedding for search comes with Phase 8c.
STATUS_QUEUED = "queued"
STATUS_PROCESSING = "processing"
STATUS_READY = "ready"
STATUS_FAILED = "failed"
VERSION_STATUSES = (STATUS_QUEUED, STATUS_PROCESSING, STATUS_READY, STATUS_FAILED)

# Pictures, charts and tables a model described (or was not asked to), kept apart from the
# file's own text so it is always clear which words were written by a model.
ASSET_IMAGE = "image"
ASSET_TABLE = "table"
ASSET_SCANNED_PAGE = "scanned_page"
ASSET_KINDS = (ASSET_IMAGE, ASSET_TABLE, ASSET_SCANNED_PAGE)
ASSET_DESCRIBED = "described"
ASSET_SKIPPED = "skipped"
ASSET_FAILED = "failed"
ASSET_STATUSES = (ASSET_DESCRIBED, ASSET_SKIPPED, ASSET_FAILED)

EVENT_OK = "ok"
EVENT_WARNING = "warning"
EVENT_ERROR = "error"
EVENT_STATUSES = (EVENT_OK, EVENT_WARNING, EVENT_ERROR)

EMBEDDING_DIMENSIONS = 768

# Phase 8e: what a model wrote about a document. A summary covers the whole document or one
# section of it; a knowledge card is one short fact, always tied to the passage it came from.
SUMMARY_DOCUMENT = "document"
SUMMARY_SECTION = "section"
SUMMARY_SCOPES = (SUMMARY_DOCUMENT, SUMMARY_SECTION)
CARD_CASE_STUDY = "case_study"  # work done for a named or described client
CARD_CAPABILITY = "capability"  # what an offering does or how we deliver it
CARD_RESULT = "result"  # a measured outcome, with its figure
CARD_CLIENT = "client"  # a client we serve, with nothing more said
CARD_CERTIFICATION = "certification"
CARD_PARTNERSHIP = "partnership"
CARD_KINDS = (
    CARD_CASE_STUDY,
    CARD_CAPABILITY,
    CARD_RESULT,
    CARD_CLIENT,
    CARD_CERTIFICATION,
    CARD_PARTNERSHIP,
)
CONFIDENCE_LEVELS = ("high", "medium", "low")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Document(Base, TimestampMixin, UpdatedAtMixin):
    """One file the team uploaded about what we sell, as the library shows it: a name, the
    offerings it is about (none = general, like a company deck), and its versions. The text lives
    on the versions; no original file is kept."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    # Null until sign-in exists (Phase 8 prepares the column).
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)

    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version",
    )


class DocumentVersion(Base, TimestampMixin):
    """One upload of a document. A changed deck is uploaded as a new version: the old one keeps
    being searched until the new one is ready, then it is archived (`is_current` false) but kept
    for audit. Pages, chunks, assets and events belong to a version."""

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version"),
        # The same bytes are never stored twice for an organisation, whatever the file is called.
        UniqueConstraint("organization_id", "content_hash"),
        CheckConstraint(_in("media_type", MEDIA_TYPES), name="media_type"),
        CheckConstraint(_in("status", VERSION_STATUSES), name="status"),
        # At most one current version per document.
        Index(
            "uq_document_versions_one_current",
            "document_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    original_filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(10))
    # SHA-256 of the uploaded bytes: duplicate detection, never used to find a file (none is kept).
    content_hash: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(12), default=STATUS_QUEUED)
    error: Mapped[str | None] = mapped_column(String(500))
    page_count: Mapped[int | None] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document: Mapped[Document] = relationship(back_populates="versions")


class DocumentUpload(Base):
    """The uploaded bytes, only until the background job has read them. Deleted as soon as the
    text is extracted; a failed one is purged after a retention period (reprocess needs it until
    then). This is what "no original file is kept" means: a short-lived staging row."""

    __tablename__ = "document_uploads"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), unique=True
    )
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DocumentPage(Base):
    """Everything a file said on one page, slide or section, in reading order, so nothing in the
    file is lost even where chunking splits it. Image and table descriptions appear inline as
    `[IMAGE: ...]` / `[TABLE: ...]`, and are listed in `document_assets` with who wrote them."""

    __tablename__ = "document_pages"
    __table_args__ = (UniqueConstraint("version_id", "position"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)  # 1-based order in the file
    locator: Mapped[str] = mapped_column(String(80))  # "Page 4", "Slide 7", "Pricing"
    heading_path: Mapped[str | None] = mapped_column(String(500))
    text: Mapped[str] = mapped_column(Text)


class DocumentAsset(Base):
    """A picture, chart, table or scanned page that a model described (Gemini vision), or that was
    skipped or failed. The words here are written by a model, so every row records which model and
    prompt version wrote it (docs/ai-governance.md, G9) and what it cost."""

    __tablename__ = "document_assets"
    __table_args__ = (
        CheckConstraint(_in("kind", ASSET_KINDS), name="kind"),
        CheckConstraint(_in("status", ASSET_STATUSES), name="status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    locator: Mapped[str] = mapped_column(String(80))
    position: Mapped[int] = mapped_column(Integer)  # order within the whole file
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(10))
    description: Mapped[str | None] = mapped_column(Text)
    # Why it was skipped or failed, in plain words.
    note: Mapped[str | None] = mapped_column(String(500))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    provider: Mapped[str | None] = mapped_column(String(30))
    model_used: Mapped[str | None] = mapped_column(String(60))
    prompt_version: Mapped[str | None] = mapped_column(String(20))
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    est_cost_usd: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DocumentChunk(Base):
    """A passage of a version, the unit that search will find (Phase 8c). Verbatim file text plus
    the stored image descriptions, so it is not model-written content in its own right."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("version_id", "ordinal"),
        Index("ix_document_chunks_tsv", "tsv", postgresql_using="gin"),
        # Nearest-neighbour search by cosine distance (created by migration d5b9f2a73c18).
        Index(
            "ix_document_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    locator: Mapped[str] = mapped_column(String(80))
    heading_path: Mapped[str | None] = mapped_column(String(500))
    text: Mapped[str] = mapped_column(Text)
    char_count: Mapped[int] = mapped_column(Integer)
    # Filled by Phase 8c. The model that made the vector is recorded so a change re-embeds rather
    # than mixing two vector spaces.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    embedding_model: Mapped[str | None] = mapped_column(String(60))
    # Full-text search over the chunk, kept by the database itself.
    tsv: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', text)", persisted=True), deferred=True
    )


class DocumentOffering(Base):
    """Which offerings a document is about. A document with none is general (a company deck).
    Detaching an offering never deletes the document."""

    __tablename__ = "document_offerings"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class DocumentIngestionEvent(Base):
    """One line of what happened while a version was processed (read, describe images, chunk, ...)
    with timings and errors, so a slow or failed upload can be explained."""

    __tablename__ = "document_ingestion_events"
    __table_args__ = (CheckConstraint(_in("status", EVENT_STATUSES), name="status"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    step: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(10))
    message: Mapped[str] = mapped_column(String(500))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DocumentSummary(Base):
    """A short summary of a version, written by a model: one for the whole document and one per
    section (a run of pages or slides). Model-written, so it records which model and prompt wrote
    it (G9); the whole-document row also carries what summarising the version cost."""

    __tablename__ = "document_summaries"
    __table_args__ = (
        UniqueConstraint("version_id", "scope", "position"),
        CheckConstraint(_in("scope", SUMMARY_SCOPES), name="scope"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    scope: Mapped[str] = mapped_column(String(10))
    position: Mapped[int] = mapped_column(Integer)  # 0 for the document, 1.. for sections
    locator: Mapped[str] = mapped_column(String(80))  # "Slides 1-6", or the file's page range
    text: Mapped[str] = mapped_column(Text)
    model_used: Mapped[str | None] = mapped_column(String(60))
    prompt_version: Mapped[str | None] = mapped_column(String(20))
    # On the document row only: the estimated cost of every model call that summarised the version.
    est_cost_usd: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class KnowledgeCard(Base):
    """One short fact a model pulled from a document ("Moved 40 plants to Azure for a car maker"),
    tied to the passage it came from and to a verbatim quote that code checked is in it. Cards are
    what the flows see first from our documents: shorter and sharper than whole passages.

    The client, industry and offering columns are kept so a graph of who-we-did-what-for can be
    built later without reading the cards again. A wrong card is hidden by a person, never edited:
    its words stay the model's own (G9)."""

    __tablename__ = "knowledge_cards"
    __table_args__ = (
        UniqueConstraint("version_id", "position"),
        CheckConstraint(_in("kind", CARD_KINDS), name="kind"),
        CheckConstraint(_in("confidence", CONFIDENCE_LEVELS), name="confidence"),
        Index("ix_knowledge_cards_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_knowledge_cards_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    # The passage the fact came from; the quote below is found in its text.
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)  # order within the version
    kind: Mapped[str] = mapped_column(String(20))
    statement: Mapped[str] = mapped_column(String(600))
    quote: Mapped[str] = mapped_column(Text)
    # Only when the passage names them; never guessed.
    client: Mapped[str | None] = mapped_column(String(255))
    industry: Mapped[str | None] = mapped_column(String(120))
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), index=True
    )
    confidence: Mapped[str] = mapped_column(String(10))
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    model_used: Mapped[str | None] = mapped_column(String(60))
    prompt_version: Mapped[str | None] = mapped_column(String(20))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    embedding_model: Mapped[str | None] = mapped_column(String(60))
    tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', statement || ' ' || coalesce(client, '') || ' ' || "
            "coalesce(industry, ''))",
            persisted=True,
        ),
        deferred=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


AUDIT_UPLOADED = "uploaded"
AUDIT_NEW_VERSION = "new_version"
AUDIT_READ_AGAIN = "read_again"
AUDIT_RENAMED = "renamed"
AUDIT_DELETED = "deleted"
# Phase 8e: a person hid a knowledge card (or showed it again), or asked for a new summary.
AUDIT_CARD_HIDDEN = "card_hidden"
AUDIT_CARD_SHOWN = "card_shown"
AUDIT_SUMMARISE = "summarise"
AUDIT_ACTIONS = (
    AUDIT_UPLOADED,
    AUDIT_NEW_VERSION,
    AUDIT_READ_AGAIN,
    AUDIT_RENAMED,
    AUDIT_DELETED,
    AUDIT_CARD_HIDDEN,
    AUDIT_CARD_SHOWN,
    AUDIT_SUMMARISE,
)


class DocumentAudit(Base):
    """Who did what to the library, kept even after a document is deleted. The document is named
    here by a plain id and name (no foreign key) because the row must outlive it; the ingestion
    events, by contrast, go with the document."""

    __tablename__ = "document_audit"
    __table_args__ = (CheckConstraint(_in("action", AUDIT_ACTIONS), name="action"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(index=True)
    document_name: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(12))
    detail: Mapped[str | None] = mapped_column(String(500))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
