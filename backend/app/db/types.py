from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

# The type every JSON column uses: JSONB on Postgres (stored parsed, comparable, indexable when a
# query ever needs it) and plain JSON elsewhere, so the in-memory SQLite test database still
# builds the same tables.
JsonB = JSON().with_variant(JSONB(), "postgresql")
