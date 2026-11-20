"""document_audit: a record of library actions that survives deleting a document

Revision ID: c7a4e1d92b38
Revises: b9f3d5a71c62
Create Date: 2026-11-20

Phase 8b follow-up. Only a new table; nothing that exists is changed. Deleting a document removes its
ingestion events with it, so this keeps one line per upload, new version, re-read, rename and delete.
"""

import sqlalchemy as sa
from alembic import op

revision = "c7a4e1d92b38"
down_revision = "b9f3d5a71c62"
branch_labels = None
depends_on = None

_ACTIONS = ("uploaded", "new_version", "read_again", "renamed", "deleted")


def upgrade() -> None:
    op.create_table(
        "document_audit",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_name", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=12), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.CheckConstraint(
            f"action IN ({', '.join(repr(a) for a in _ACTIONS)})",
            name=op.f("ck_document_audit_action"),
        ),
    )
    op.create_index("ix_document_audit_organization_id", "document_audit", ["organization_id"])
    op.create_index("ix_document_audit_document_id", "document_audit", ["document_id"])
    op.create_index("ix_document_audit_user_id", "document_audit", ["user_id"])


def downgrade() -> None:
    op.drop_table("document_audit")
