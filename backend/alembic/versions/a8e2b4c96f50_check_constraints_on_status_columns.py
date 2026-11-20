"""check constraints on status-like columns

Revision ID: a8e2b4c96f50
Revises: f6d1a3b85e49
Create Date: 2026-11-20

Phase 8a. Every string column that holds a fixed set of values gets a CHECK constraint, so a typo or
a stray value is refused by the database instead of being stored and silently mis-counted. The sets
come from the code (every place that writes each column was traced) and every value already stored
was confirmed to be inside its set before this was written. NULL still passes on nullable columns.

Deliberately not constrained: `jobs.job_type` (grows with every new job type; the worker refuses an
unknown one) and `contacts.seniority` (never written yet, meant for free text).

Adding a new value in code means a new migration that drops and re-adds that column's constraint.
The local test tests/unit/test_status_checks.py fails when a code constant and its constraint disagree.
`offering_proposals.status` allows "withdrawn": the code sets it just before deleting the row.
"""

from alembic import op

revision = "a8e2b4c96f50"
down_revision = "f6d1a3b85e49"
branch_labels = None
depends_on = None

ALLOWED: dict[tuple[str, str], tuple[str, ...]] = {
    ("api_usage", "kind"): ("llm", "search", "credits"),
    ("api_usage", "status"): ("ok", "error"),
    ("companies", "enrichment_status"): ("never_enriched", "pending", "enriched", "failed"),
    ("company_opportunities", "status"): ("suggested", "active", "archived"),
    ("company_opportunities", "suggestion_source"): ("searched", "evidence", "next_best"),
    ("contact_channels", "channel_type"): ("email", "phone", "linkedin"),
    ("contact_channels", "verification_status"): ("unverified", "valid", "invalid", "unknown"),
    ("contact_opportunity_relevance", "role"): (
        "decision_maker",
        "influencer",
        "user",
        "not_relevant",
        "revert",
    ),
    ("contact_opportunity_relevance", "source"): ("model", "human"),
    ("contacts", "next_follow_up_channel"): ("email", "linkedin"),
    ("contacts", "status"): (
        "not_contacted",
        "contacted",
        "follow_up_scheduled",
        "responded",
        "not_a_fit",
    ),
    ("drafts", "channel"): ("email",),
    ("drafts", "draft_type"): ("first_touch", "follow_up", "follow_up_2", "follow_up_3"),
    ("drafts", "status"): ("draft", "sent", "discarded"),
    ("enrichment_records", "entity_type"): ("company", "contact"),
    ("ingestion_runs", "source_type"): ("csv", "market_discovery"),
    ("ingestion_runs", "status"): ("pending", "running", "done", "failed", "awaiting_confirmation"),
    ("jobs", "status"): ("pending", "running", "done", "failed"),
    ("offering_pages", "lane"): ("site", "extra", "post", "menu"),
    ("offering_pages", "verdict"): ("offering", "not_offering", "failed"),
    ("offering_proposals", "kind"): ("service", "product"),
    ("offering_proposals", "status"): ("pending", "approved", "rejected", "withdrawn"),
    ("opportunity_assessments", "verdict"): (
        "supported",
        "emerging",
        "weak",
        "insufficient_evidence",
    ),
    ("opportunity_offering_matches", "band"): (
        "strong",
        "potential",
        "weak",
        "insufficient_evidence",
    ),
    ("outreach_activities", "activity_type"): ("sent", "response_received"),
    ("outreach_activities", "channel"): ("email", "linkedin"),
    ("outreach_activities", "outcome"): (
        "interested",
        "not_now",
        "not_interested",
        "referred",
        "out_of_office",
    ),
    ("products", "kind"): ("service", "product"),
    ("products", "profile_status"): ("generated", "edited"),
    ("products", "source"): ("manual", "website"),
    ("products", "status"): ("active", "archived"),
    ("qualification_results", "overall_verdict"): (
        "qualified",
        "not_qualified",
        "could_not_determine",
        "not_checked",
    ),
    ("review_decisions", "decision"): ("confirmed", "deleted", "not_a_fit", "restored"),
    ("review_decisions", "reason_code"): (
        "wrong_industry",
        "wrong_size",
        "wrong_location",
        "not_a_real_company",
        "already_a_customer",
        "other",
    ),
    ("review_decisions", "subject_type"): ("company", "contact"),
    ("role_relevance_results", "priority"): ("primary", "secondary", "not_relevant"),
}


def _name(table: str, column: str) -> str:
    # op.f: the name is final; without it Alembic would apply the "ck_<table>_" convention again.
    return op.f(f"ck_{table}_{column}")


# e5c9f2a74d38 first named its checks without op.f, so on databases migrated before that was fixed
# they carry the "ck_<table>_" prefix twice (cut and hashed by Postgres' 63-character limit). Give
# each its intended name, found by the column it checks. On a database built since, nothing matches.
_RENAME_CRITERION_CHECKS = """
DO $$
DECLARE r record;
BEGIN
    FOR r IN
        SELECT c.conname, a.attname
        FROM pg_constraint c
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
        WHERE c.conrelid = 'qualification_criterion_results'::regclass
          AND c.contype = 'c'
          AND c.conname <> 'ck_qualification_criterion_results_' || a.attname
    LOOP
        EXECUTE format(
            'ALTER TABLE qualification_criterion_results RENAME CONSTRAINT %I TO %I',
            r.conname,
            'ck_qualification_criterion_results_' || r.attname
        );
    END LOOP;
END $$;
"""


def upgrade() -> None:
    op.execute(_RENAME_CRITERION_CHECKS)
    for (table, column), values in ALLOWED.items():
        listed = ", ".join(f"'{v}'" for v in values)
        op.create_check_constraint(_name(table, column), table, f"{column} IN ({listed})")


def downgrade() -> None:
    for table, column in reversed(list(ALLOWED)):
        op.drop_constraint(_name(table, column), table, type_="check")
