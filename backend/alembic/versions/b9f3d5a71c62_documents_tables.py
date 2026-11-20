"""documents: library, versions, pages, assets, chunks, staging uploads, events

Revision ID: b9f3d5a71c62
Revises: a8e2b4c96f50
Create Date: 2026-11-20

Phase 8b. Adds the tables behind the documents knowledge base. Only new tables: nothing that exists
is changed. `document_chunks.embedding` (pgvector) and the full-text column are created now and
filled by Phase 8c; the vector index is added then, once there are vectors to index.

Needs the `vector` extension (enabled by b2f6c8d41a05).
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "b9f3d5a71c62"
down_revision = "a8e2b4c96f50"
branch_labels = None
depends_on = None


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _fk(column: str, target: str, ondelete: str | None = None) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint([column], [target], ondelete=ondelete)


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        _fk("organization_id", "organizations.id"),
        _fk("uploaded_by", "users.id"),
    )
    op.create_index("ix_documents_organization_id", "documents", ["organization_id"])
    op.create_index("ix_documents_uploaded_by", "documents", ["uploaded_by"])

    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=10), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        _fk("organization_id", "organizations.id"),
        _fk("document_id", "documents.id", ondelete="CASCADE"),
        sa.UniqueConstraint("document_id", "version"),
        sa.UniqueConstraint("organization_id", "content_hash"),
        sa.CheckConstraint(
            _in("media_type", ("pdf", "pptx", "docx", "md", "txt")),
            name=op.f("ck_document_versions_media_type"),
        ),
        sa.CheckConstraint(
            _in("status", ("queued", "processing", "ready", "failed")),
            name=op.f("ck_document_versions_status"),
        ),
    )
    op.create_index(
        "ix_document_versions_organization_id", "document_versions", ["organization_id"]
    )
    op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"])
    op.create_index(
        "uq_document_versions_one_current",
        "document_versions",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )

    op.create_table(
        "document_uploads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        _fk("version_id", "document_versions.id", ondelete="CASCADE"),
        sa.UniqueConstraint("version_id"),
    )

    op.create_table(
        "document_pages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("locator", sa.String(length=80), nullable=False),
        sa.Column("heading_path", sa.String(length=500), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        _fk("document_id", "documents.id", ondelete="CASCADE"),
        _fk("version_id", "document_versions.id", ondelete="CASCADE"),
        sa.UniqueConstraint("version_id", "position"),
    )
    op.create_index("ix_document_pages_document_id", "document_pages", ["document_id"])
    op.create_index("ix_document_pages_version_id", "document_pages", ["version_id"])

    op.create_table(
        "document_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("locator", sa.String(length=80), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=30), nullable=True),
        sa.Column("model_used", sa.String(length=60), nullable=True),
        sa.Column("prompt_version", sa.String(length=20), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("est_cost_usd", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        _fk("organization_id", "organizations.id"),
        _fk("document_id", "documents.id", ondelete="CASCADE"),
        _fk("version_id", "document_versions.id", ondelete="CASCADE"),
        sa.CheckConstraint(
            _in("kind", ("image", "table", "scanned_page")), name=op.f("ck_document_assets_kind")
        ),
        sa.CheckConstraint(
            _in("status", ("described", "skipped", "failed")),
            name=op.f("ck_document_assets_status"),
        ),
    )
    op.create_index("ix_document_assets_organization_id", "document_assets", ["organization_id"])
    op.create_index("ix_document_assets_document_id", "document_assets", ["document_id"])
    op.create_index("ix_document_assets_version_id", "document_assets", ["version_id"])

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("locator", sa.String(length=80), nullable=False),
        sa.Column("heading_path", sa.String(length=500), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column("embedding_model", sa.String(length=60), nullable=True),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', text)", persisted=True),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        _fk("organization_id", "organizations.id"),
        _fk("document_id", "documents.id", ondelete="CASCADE"),
        _fk("version_id", "document_versions.id", ondelete="CASCADE"),
        sa.UniqueConstraint("version_id", "ordinal"),
    )
    op.create_index("ix_document_chunks_organization_id", "document_chunks", ["organization_id"])
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_document_chunks_version_id", "document_chunks", ["version_id"])
    op.create_index("ix_document_chunks_tsv", "document_chunks", ["tsv"], postgresql_using="gin")

    op.create_table(
        "document_offerings",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("document_id", "product_id"),
        _fk("document_id", "documents.id", ondelete="CASCADE"),
        _fk("product_id", "products.id", ondelete="CASCADE"),
    )
    op.create_index("ix_document_offerings_product_id", "document_offerings", ["product_id"])

    op.create_table(
        "document_ingestion_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("step", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        _fk("document_id", "documents.id", ondelete="CASCADE"),
        _fk("version_id", "document_versions.id", ondelete="CASCADE"),
        sa.CheckConstraint(
            _in("status", ("ok", "warning", "error")),
            name=op.f("ck_document_ingestion_events_status"),
        ),
    )
    op.create_index(
        "ix_document_ingestion_events_document_id", "document_ingestion_events", ["document_id"]
    )
    op.create_index(
        "ix_document_ingestion_events_version_id", "document_ingestion_events", ["version_id"]
    )


def downgrade() -> None:
    for table in (
        "document_ingestion_events",
        "document_offerings",
        "document_chunks",
        "document_assets",
        "document_pages",
        "document_uploads",
        "document_versions",
        "documents",
    ):
        op.drop_table(table)
