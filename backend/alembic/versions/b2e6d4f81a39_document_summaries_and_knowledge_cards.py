"""document_summaries, knowledge_cards, and offering proposals drawn from documents

Revision ID: b2e6d4f81a39
Revises: a6d3f8b20c45
Create Date: 2026-11-23

Phase 8e. Two new tables for what a model writes about a document: a summary of the whole document
and of each section, and knowledge cards (one short fact each, tied to the passage it came from).
Both record the model and prompt version that wrote them (G9). Cards have a vector and a word index
so they can be searched like passages.

`offering_proposals.document_id` (nullable) links a proposal for a better offering description to
the document it was drawn from. `document_audit.action` also allows "card_hidden", "card_shown" and
"summarise" (a person hid or showed a card, or asked for a new summary). New tables, a nullable
column and a wider check only; no existing row changes.
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "b2e6d4f81a39"
down_revision = "a6d3f8b20c45"
branch_labels = None
depends_on = None

_CARD_KINDS = (
    "case_study",
    "capability",
    "result",
    "client",
    "certification",
    "partnership",
)


_AUDIT_BEFORE = ("uploaded", "new_version", "read_again", "renamed", "deleted")
_AUDIT_AFTER = (*_AUDIT_BEFORE, "card_hidden", "card_shown", "summarise")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _fk(column: str, target: str, ondelete: str | None = None) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint([column], [target], ondelete=ondelete)


def upgrade() -> None:
    op.create_table(
        "document_summaries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(length=10), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("locator", sa.String(length=80), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("model_used", sa.String(length=60), nullable=True),
        sa.Column("prompt_version", sa.String(length=20), nullable=True),
        sa.Column("est_cost_usd", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        _fk("organization_id", "organizations.id"),
        _fk("document_id", "documents.id", ondelete="CASCADE"),
        _fk("version_id", "document_versions.id", ondelete="CASCADE"),
        sa.UniqueConstraint("version_id", "scope", "position"),
        sa.CheckConstraint(
            _in("scope", ("document", "section")), name=op.f("ck_document_summaries_scope")
        ),
    )
    op.create_index(
        "ix_document_summaries_organization_id", "document_summaries", ["organization_id"]
    )
    op.create_index("ix_document_summaries_document_id", "document_summaries", ["document_id"])
    op.create_index("ix_document_summaries_version_id", "document_summaries", ["version_id"])

    op.create_table(
        "knowledge_cards",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("statement", sa.String(length=600), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("client", sa.String(length=255), nullable=True),
        sa.Column("industry", sa.String(length=120), nullable=True),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("confidence", sa.String(length=10), nullable=False),
        sa.Column("hidden", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("model_used", sa.String(length=60), nullable=True),
        sa.Column("prompt_version", sa.String(length=20), nullable=True),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column("embedding_model", sa.String(length=60), nullable=True),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('english', statement || ' ' || coalesce(client, '') || ' ' || "
                "coalesce(industry, ''))",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        _fk("organization_id", "organizations.id"),
        _fk("document_id", "documents.id", ondelete="CASCADE"),
        _fk("version_id", "document_versions.id", ondelete="CASCADE"),
        _fk("chunk_id", "document_chunks.id", ondelete="CASCADE"),
        _fk("product_id", "products.id", ondelete="SET NULL"),
        sa.UniqueConstraint("version_id", "position"),
        sa.CheckConstraint(_in("kind", _CARD_KINDS), name=op.f("ck_knowledge_cards_kind")),
        sa.CheckConstraint(
            _in("confidence", ("high", "medium", "low")),
            name=op.f("ck_knowledge_cards_confidence"),
        ),
    )
    op.create_index("ix_knowledge_cards_organization_id", "knowledge_cards", ["organization_id"])
    op.create_index("ix_knowledge_cards_document_id", "knowledge_cards", ["document_id"])
    op.create_index("ix_knowledge_cards_version_id", "knowledge_cards", ["version_id"])
    op.create_index("ix_knowledge_cards_chunk_id", "knowledge_cards", ["chunk_id"])
    op.create_index("ix_knowledge_cards_product_id", "knowledge_cards", ["product_id"])
    op.create_index("ix_knowledge_cards_tsv", "knowledge_cards", ["tsv"], postgresql_using="gin")
    op.create_index(
        "ix_knowledge_cards_embedding",
        "knowledge_cards",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.add_column("offering_proposals", sa.Column("document_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_offering_proposals_document_id_documents"),
        "offering_proposals",
        "documents",
        ["document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_offering_proposals_document_id", "offering_proposals", ["document_id"])

    op.drop_constraint(op.f("ck_document_audit_action"), "document_audit", type_="check")
    op.create_check_constraint(
        op.f("ck_document_audit_action"), "document_audit", _in("action", _AUDIT_AFTER)
    )


def downgrade() -> None:
    # The new audit actions only exist because of this phase; they go with the wider check.
    op.execute(
        "DELETE FROM document_audit WHERE action IN ('card_hidden', 'card_shown', 'summarise')"
    )
    op.drop_constraint(op.f("ck_document_audit_action"), "document_audit", type_="check")
    op.create_check_constraint(
        op.f("ck_document_audit_action"), "document_audit", _in("action", _AUDIT_BEFORE)
    )
    # Proposals drawn from documents only exist because of this phase; they go with the column.
    op.execute("DELETE FROM offering_proposals WHERE origin = 'document'")
    op.drop_index("ix_offering_proposals_document_id", table_name="offering_proposals")
    op.drop_constraint(
        op.f("fk_offering_proposals_document_id_documents"),
        "offering_proposals",
        type_="foreignkey",
    )
    op.drop_column("offering_proposals", "document_id")
    op.drop_table("knowledge_cards")
    op.drop_table("document_summaries")
