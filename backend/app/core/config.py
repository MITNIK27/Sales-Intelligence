from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "local"
    log_level: str = "INFO"
    # Off by default — SQLAlchemy's query echo dumps every single SQL statement (often twice,
    # once as its own echo handler and once via root-logger propagation), which drowns out the
    # actual application log lines (requests, job lifecycle, errors) in the terminal. Turn on
    # only when actively debugging a query itself.
    sql_echo: bool = False
    secret_key: str = "changeme"

    database_url: str = "postgresql+asyncpg://sales_intel:sales_intel@localhost:5433/sales_intel"

    gemini_api_key: str | None = None
    # A rolling alias, not a pinned version — each pinned free-tier model gets its own separate
    # small daily request quota (RESOURCE_EXHAUSTED, not a transient overload, once used up; see
    # gemini_client.py's quota-vs-overload distinction), so pinning to one specific model name
    # means every Gemini-backed feature in the app goes down together for the rest of the day
    # once that one model's quota is spent. The "latest" alias also means Google's own model
    # rollovers don't require a config change here.
    gemini_model: str = "gemini-flash-lite-latest"

    scraper_user_agent: str = "SalesIntelligenceBot/0.1 (+internal tool)"
    scraper_request_delay_seconds: float = 1.0

    # Google Custom Search JSON API — used only for domain discovery when a company has no
    # domain on file. Both unset is a valid, graceful state (GoogleCustomSearchProvider just
    # returns no match rather than erroring), so local dev works without a key.
    google_search_api_key: str | None = None
    google_search_engine_id: str | None = None

    # Serper.dev — wraps real Google SERP results, free tier (no card required). Default
    # discovery backend for both domain lookup (2a) and candidate discovery (2c), since Google
    # Custom Search no longer supports whole-web search on newly created engines.
    serper_api_key: str | None = None

    # Aggregator/directory/social domains that occasionally rank for company-search queries but
    # are never themselves the company being searched for — filtered out of Market Discovery
    # candidates so e.g. a LinkedIn company page never becomes a `Company` row.
    market_discovery_domain_denylist: list[str] = [
        "linkedin.com",
        "indeed.com",
        "crunchbase.com",
        "glassdoor.com",
        "facebook.com",
        "twitter.com",
        "x.com",
        "wikipedia.org",
        "ziprecruiter.com",
        "monster.com",
        "apollo.io",
        "ycombinator.com",
        "google.com",
        "youtube.com",
    ]

    # Discovery Agent (Phase A1, see docs/decisions/0004-discovery-agent.md) — which free-tier
    # Gemini model powers the extraction stage specifically. Kept separate from `gemini_model`
    # so this one failure-sensitive stage can use a stronger free-tier model (e.g. a "pro"
    # variant) than the rest of the app without changing every other Gemini call. Empty string
    # (default) means "use `gemini_model`".
    discovery_agent_extraction_model: str = ""
    # Results requested per search-query variant (the gatherer issues several variants per run —
    # see search_gatherer.py — so this is per-query, not the total candidate count).
    discovery_agent_results_per_query: int = 10
    # Bounded fan-out for per-company domain resolution after extraction.
    discovery_agent_resolution_concurrency: int = 5

    # Phase C — Tracker & Cadence Mechanics (outreach/cadence.py). How many business days after a
    # "sent" outreach activity the next follow-up gets auto-scheduled, when not overridden.
    default_follow_up_gap_business_days: int = 3
    # IANA timezone name used for send-window math when a contact has no `timezone` of their own
    # set — most won't, initially, so this is the fallback, not a hard per-contact requirement.
    default_timezone: str = "UTC"


@lru_cache
def get_settings() -> Settings:
    return Settings()
