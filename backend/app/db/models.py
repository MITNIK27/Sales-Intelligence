"""Import every module's models here so they're registered on Base's mapper registry
before any mapper configuration runs (SQLAlchemy relationship/FK resolution needs every
mapped class to have been imported at least once). Import this module — not the
individual model modules — from app entrypoints (app.main, the worker, alembic/env.py)."""

from app.modules.ai_recommendation import models as ai_recommendation_models  # noqa: F401
from app.modules.auth import models as auth_models  # noqa: F401
from app.modules.companies import models as companies_models  # noqa: F401
from app.modules.contacts import models as contacts_models  # noqa: F401
from app.modules.draft import models as draft_models  # noqa: F401
from app.modules.enrichment import models as enrichment_models  # noqa: F401
from app.modules.ingestion import models as ingestion_models  # noqa: F401
from app.modules.jobs import models as jobs_models  # noqa: F401
from app.modules.outreach import models as outreach_models  # noqa: F401
from app.modules.products import models as products_models  # noqa: F401
from app.modules.qualification import models as qualification_models  # noqa: F401
from app.modules.role_relevance import models as role_relevance_models  # noqa: F401
