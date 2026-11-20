"""users for firebase sign-in, and who made each review decision

Revision ID: f6d1a3b85e49
Revises: e5c9f2a74d38
Create Date: 2026-11-20

Phase 8a. Sign-in will be Firebase Authentication, so `users` no longer stores a password: it gets
`firebase_uid` (the link to the Firebase account), `display_name`, `status` and `last_sign_in_at`,
and `role` becomes one of admin | manager | rep. The table has never been used (no sign-in yet), so
it is reshaped directly; the migration stops without changing anything if it finds any row.

`review_decisions.user_id`: who decided, null until sign-in exists. A real foreign key, because users
are disabled rather than deleted.
"""

import sqlalchemy as sa
from alembic import op

revision = "f6d1a3b85e49"
down_revision = "e5c9f2a74d38"
branch_labels = None
depends_on = None

_REQUIRE_EMPTY = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM users) THEN
        RAISE EXCEPTION 'users has rows; this migration assumes the table was never used';
    END IF;
END $$;
"""


def upgrade() -> None:
    op.execute(_REQUIRE_EMPTY)
    op.drop_column("users", "hashed_password")
    op.add_column("users", sa.Column("firebase_uid", sa.String(length=128), nullable=False))
    op.create_unique_constraint("uq_users_firebase_uid", "users", ["firebase_uid"])
    op.add_column("users", sa.Column("display_name", sa.String(length=255), nullable=True))
    op.alter_column(
        "users",
        "role",
        type_=sa.String(length=20),
        existing_type=sa.String(length=50),
        server_default="rep",
    )
    op.add_column(
        "users",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
    )
    op.add_column("users", sa.Column("last_sign_in_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_check_constraint(
        op.f("ck_users_role"), "users", "role IN ('admin', 'manager', 'rep')"
    )
    op.create_check_constraint(op.f("ck_users_status"), "users", "status IN ('active', 'disabled')")

    op.add_column("review_decisions", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_review_decisions_user_id_users", "review_decisions", "users", ["user_id"], ["id"]
    )
    op.create_index("ix_review_decisions_user_id", "review_decisions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_review_decisions_user_id", table_name="review_decisions")
    op.drop_constraint("fk_review_decisions_user_id_users", "review_decisions", type_="foreignkey")
    op.drop_column("review_decisions", "user_id")

    op.execute(_REQUIRE_EMPTY)
    op.drop_constraint(op.f("ck_users_status"), "users", type_="check")
    op.drop_constraint(op.f("ck_users_role"), "users", type_="check")
    op.drop_column("users", "updated_at")
    op.drop_column("users", "last_sign_in_at")
    op.drop_column("users", "status")
    op.alter_column(
        "users",
        "role",
        type_=sa.String(length=50),
        existing_type=sa.String(length=20),
        server_default="member",
    )
    op.drop_column("users", "display_name")
    op.drop_constraint("uq_users_firebase_uid", "users", type_="unique")
    op.drop_column("users", "firebase_uid")
    op.add_column("users", sa.Column("hashed_password", sa.String(length=255), nullable=False))
