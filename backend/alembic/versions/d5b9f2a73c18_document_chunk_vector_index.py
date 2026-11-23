"""document_chunks: HNSW index for nearest-neighbour search

Revision ID: d5b9f2a73c18
Revises: c7a4e1d92b38
Create Date: 2026-11-20

Phase 8c. Only an index; no data changes. HNSW (cosine) answers "which passages are nearest this
question" without comparing against every row. Passages without a vector are simply not in it.
Built on a table that is small today; a large one should be built outside a transaction.
"""

from alembic import op

revision = "d5b9f2a73c18"
down_revision = "c7a4e1d92b38"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_document_chunks_embedding",
        "document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_embedding", table_name="document_chunks")
