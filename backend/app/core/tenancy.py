import uuid

# Fixed id for the single seeded "Internal" organization used while no auth/login exists yet
# (see migration 0002 and docs/decisions for context). Every table already carries
# organization_id, so wiring up real multi-user auth later only means populating this from a
# session instead of a constant — not a schema change.
DEFAULT_ORGANIZATION_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
