from fastapi import FastAPI

from app.api.v1.companies import router as companies_router
from app.api.v1.contacts import router as contacts_router
from app.api.v1.drafts import company_router as draft_company_router
from app.api.v1.drafts import draft_router
from app.api.v1.enrichment import router as enrichment_router
from app.api.v1.health import router as health_router
from app.api.v1.ingestion import router as ingestion_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.market_discovery import router as market_discovery_router
from app.api.v1.outreach import router as outreach_router
from app.api.v1.products import router as products_router
from app.api.v1.qualification import check_router as qualification_check_router
from app.api.v1.qualification import company_router as qualification_company_router
from app.api.v1.qualification import router as qualification_router
from app.api.v1.recommendations import router as recommendations_router
from app.api.v1.role_relevance import category_router as role_category_router
from app.api.v1.role_relevance import company_router as role_relevance_company_router
from app.core.logging import configure_logging
from app.db import models as _models  # noqa: F401 - registers all models with SQLAlchemy

configure_logging()

app = FastAPI(title="Sales Intelligence API", version="0.1.0")

app.include_router(health_router, prefix="/api/v1")
app.include_router(ingestion_router, prefix="/api/v1")
app.include_router(jobs_router, prefix="/api/v1")
app.include_router(companies_router, prefix="/api/v1")
app.include_router(contacts_router, prefix="/api/v1")
app.include_router(draft_company_router, prefix="/api/v1")
app.include_router(draft_router, prefix="/api/v1")
app.include_router(enrichment_router, prefix="/api/v1")
app.include_router(market_discovery_router, prefix="/api/v1")
app.include_router(outreach_router, prefix="/api/v1")
app.include_router(products_router, prefix="/api/v1")
app.include_router(qualification_router, prefix="/api/v1")
app.include_router(qualification_company_router, prefix="/api/v1")
app.include_router(qualification_check_router, prefix="/api/v1")
app.include_router(recommendations_router, prefix="/api/v1")
app.include_router(role_category_router, prefix="/api/v1")
app.include_router(role_relevance_company_router, prefix="/api/v1")
