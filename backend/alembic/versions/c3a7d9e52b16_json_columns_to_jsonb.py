"""json columns to jsonb

Revision ID: c3a7d9e52b16
Revises: b2f6c8d41a05
Create Date: 2026-11-20

Phase 8a. Every JSON column becomes JSONB (stored parsed). Values are unchanged; only formatting
is normalised (key order, whitespace, and a duplicate key keeps its last value, which Python never
writes). scripts/db_verify.py compares these columns as parsed values, so a before/after snapshot
shows them as "type json -> jsonb, values unchanged". Each ALTER rewrites its table, which is quick
at our size; on a large production table schedule it in a quiet window.

`companies.criteria` has a server default ('[]'), which is dropped and re-added around the change.
"""

from alembic import op

revision = "c3a7d9e52b16"
down_revision = "b2f6c8d41a05"
branch_labels = None
depends_on = None

COLUMNS = (
    ("companies", "discovery_evidence"),
    ("companies", "field_provenance"),
    ("companies", "criteria"),
    ("company_opportunities", "research_log"),
    ("company_snapshots", "summary"),
    ("company_snapshots", "sources"),
    ("drafts", "grounding_flags"),
    ("drafts", "revisions"),
    ("enrichment_records", "raw_payload"),
    ("ingestion_runs", "summary"),
    ("ingestion_runs", "parsed_fields"),
    ("ingestion_runs", "context"),
    ("jobs", "payload"),
    ("jobs", "progress"),
    ("jobs", "result"),
    ("offering_pages", "extra"),
    ("offering_proposals", "grounding_flags"),
    ("opportunity_assessments", "findings"),
    ("opportunity_assessments", "not_found"),
    ("opportunity_offering_matches", "factors"),
    ("opportunity_offering_matches", "evidence"),
    ("products", "buyer_profile"),
    ("qualification_results", "criteria_results"),
    ("qualification_results", "score_breakdown"),
    ("recommendations", "talking_points"),
    ("review_decisions", "snapshot"),
)


def _convert(to_type: str) -> None:
    op.execute("ALTER TABLE companies ALTER COLUMN criteria DROP DEFAULT")
    for table, column in COLUMNS:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {to_type} USING {column}::{to_type}"
        )
    op.execute(f"ALTER TABLE companies ALTER COLUMN criteria SET DEFAULT '[]'::{to_type}")


def upgrade() -> None:
    _convert("jsonb")


def downgrade() -> None:
    _convert("json")
