"""add criteria to companies

Revision ID: a7c3e9d15b24
Revises: e2f7a9c14b68
Create Date: 2026-11-03 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7c3e9d15b24"
down_revision: str | None = "e2f7a9c14b68"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Criteria now belong to the company (typed on its page or by the search that found it), not
    # to a shared saved list. Existing companies start with none.
    op.add_column(
        "companies",
        sa.Column("criteria", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("companies", "criteria")
