"""knowledge_refs on offering fits and recommendations

Revision ID: f4a8c2e61b97
Revises: e3c7a9b14d62
Create Date: 2026-11-23

Phase 8d. Fits and recommendations record which passages from our own documents the model was shown
(and which it cited), so a person can see where a claim about an offering came from. Fits also keep a
fingerprint of the library, so they are judged again when the documents change. New nullable
columns only; existing rows are untouched.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f4a8c2e61b97"
down_revision = "e3c7a9b14d62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "opportunity_offering_matches",
        sa.Column("knowledge_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "opportunity_offering_matches",
        sa.Column("knowledge_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "recommendations",
        sa.Column("knowledge_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("recommendations", "knowledge_refs")
    op.drop_column("opportunity_offering_matches", "knowledge_hash")
    op.drop_column("opportunity_offering_matches", "knowledge_refs")
