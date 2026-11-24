"""sign-in: invitations, access requests, and who started each job and model call

Revision ID: c8f3a1d6e927
Revises: b2e6d4f81a39
Create Date: 2026-11-24

Phase 9a. Access is by invitation: an invited person has a `users` row before their first sign-in,
so `users.firebase_uid` becomes nullable (still unique) and `users.invited_by` says who invited them.
`access_requests` holds requests from people who signed in without an invitation.
`jobs.created_by` and `api_usage.user_id` record whose action started a job or a model call.

New table and nullable columns only; no existing row changes. The downgrade removes invitations that
were never used (rows without `firebase_uid`), since the old schema cannot hold them.
"""

import sqlalchemy as sa
from alembic import op

revision = "c8f3a1d6e927"
down_revision = "b2e6d4f81a39"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "firebase_uid", existing_type=sa.String(length=128), nullable=True)
    op.add_column("users", sa.Column("invited_by", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_users_invited_by_users"), "users", "users", ["invited_by"], ["id"]
    )
    op.create_index("ix_users_invited_by", "users", ["invited_by"])

    op.create_table(
        "access_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("firebase_uid", sa.String(length=128), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notify_error", sa.String(length=300), nullable=True),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"]),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'dismissed')",
            name=op.f("ck_access_requests_status"),
        ),
    )
    op.create_index("ix_access_requests_organization_id", "access_requests", ["organization_id"])
    op.create_index("ix_access_requests_email", "access_requests", ["email"])
    op.create_index("ix_access_requests_status", "access_requests", ["status"])
    op.create_index("ix_access_requests_decided_by", "access_requests", ["decided_by"])

    op.add_column("jobs", sa.Column("created_by", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_jobs_created_by_users"),
        "jobs",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_jobs_created_by", "jobs", ["created_by"])

    op.add_column("api_usage", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.create_index("ix_api_usage_user_id", "api_usage", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_api_usage_user_id", table_name="api_usage")
    op.drop_column("api_usage", "user_id")

    op.drop_index("ix_jobs_created_by", table_name="jobs")
    op.drop_constraint(op.f("fk_jobs_created_by_users"), "jobs", type_="foreignkey")
    op.drop_column("jobs", "created_by")

    op.drop_table("access_requests")

    op.drop_index("ix_users_invited_by", table_name="users")
    op.drop_constraint(op.f("fk_users_invited_by_users"), "users", type_="foreignkey")
    op.drop_column("users", "invited_by")
    # Invitations nobody used cannot exist in the old schema (firebase_uid was required).
    op.execute("DELETE FROM users WHERE firebase_uid IS NULL")
    op.alter_column("users", "firebase_uid", existing_type=sa.String(length=128), nullable=False)
