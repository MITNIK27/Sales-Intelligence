from fastapi import Depends, FastAPI

from app.api.v1.auth import auth_router, users_router
from app.api.v1.companies import router as companies_router
from app.api.v1.contacts import router as contacts_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.documents import router as documents_router
from app.api.v1.documents import status_router as documents_status_router
from app.api.v1.drafts import company_router as draft_company_router
from app.api.v1.drafts import draft_router
from app.api.v1.enrichment import router as enrichment_router
from app.api.v1.health import router as health_router
from app.api.v1.ingestion import router as ingestion_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.market_discovery import router as market_discovery_router
from app.api.v1.offerings import router as offerings_router
from app.api.v1.opportunities import company_router as opportunity_company_router
from app.api.v1.opportunities import router as opportunities_router
from app.api.v1.outreach import router as outreach_router
from app.api.v1.products import router as products_router
from app.api.v1.qualification import check_router as qualification_check_router
from app.api.v1.qualification import company_router as qualification_company_router
from app.api.v1.quicklook import router as quicklook_router
from app.api.v1.recommendations import router as recommendations_router
from app.api.v1.role_relevance import category_router as role_category_router
from app.api.v1.role_relevance import company_router as role_relevance_company_router
from app.api.v1.usage import router as usage_router
from app.core.logging import configure_logging
from app.db import models as _models  # noqa: F401 - registers all models with SQLAlchemy
from app.modules.auth.deps import signed_in
from app.modules.usage.route_tag import tag_usage_with_route

configure_logging()

app = FastAPI(
    title="Sales Intelligence API",
    version="0.1.0",
    dependencies=[Depends(tag_usage_with_route)],
)

# Open without signing in: the health check, and the endpoints for a person whose Google account is
# verified but who has no access yet (who am I, ask for access).
app.include_router(health_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")

# Everything else needs a signed-in person with an active account (Phase 9). A route left out of
# this list would be open; governance_checks/test_routes_require_sign_in.py fails if that happens.
_SIGNED_IN = [Depends(signed_in)]
for router in (
    users_router,
    ingestion_router,
    jobs_router,
    companies_router,
    contacts_router,
    dashboard_router,
    usage_router,
    documents_status_router,  # before documents: /documents/status
    documents_router,
    draft_company_router,
    draft_router,
    enrichment_router,
    market_discovery_router,
    outreach_router,
    offerings_router,  # before products: /products/sync
    opportunities_router,
    opportunity_company_router,
    products_router,
    qualification_company_router,
    qualification_check_router,
    quicklook_router,
    recommendations_router,
    role_category_router,
    role_relevance_company_router,
):
    app.include_router(router, prefix="/api/v1", dependencies=_SIGNED_IN)
