"""index the foreign keys that had no index

Revision ID: d4b8e1f63c27
Revises: c3a7d9e52b16
Create Date: 2026-11-20

Phase 8a. Postgres does not index a foreign key column by itself. Without an index, every lookup
by these columns and every delete of a parent row scans the whole child table. Adds one plain
index per column, named as SQLAlchemy names `index=True` columns, matching the models. Additive
only. On a large production table use CREATE INDEX CONCURRENTLY outside a transaction instead.
"""

from alembic import op

revision = "d4b8e1f63c27"
down_revision = "c3a7d9e52b16"
branch_labels = None
depends_on = None

FOREIGN_KEYS = (
    ("users", "organization_id"),
    ("ingestion_runs", "created_by_user_id"),
    ("companies", "source_ingestion_run_id"),
    ("recommendations", "contact_id"),
    ("recommendations", "opportunity_assessment_id"),
    ("recommendations", "product_id"),
    ("role_relevance_results", "matched_category_id"),
    ("outreach_activities", "draft_id"),
    ("drafts", "product_id"),
    ("drafts", "recommendation_id"),
    ("company_opportunities", "created_by_run_id"),
    ("opportunity_offering_matches", "assessment_id"),
    ("contact_opportunity_relevance", "assessment_id"),
    ("contact_opportunity_relevance", "product_id"),
)


def upgrade() -> None:
    for table, column in FOREIGN_KEYS:
        op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    for table, column in reversed(FOREIGN_KEYS):
        op.drop_index(f"ix_{table}_{column}", table_name=table)
