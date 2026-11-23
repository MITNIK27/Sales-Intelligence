from functools import lru_cache
from typing import Literal

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

    database_url: str = "postgresql+asyncpg://sales_intel:sales_intel@localhost:5435/sales_intel"
    # Alembic uses this when set (on a hosted database, the direct connection with the schema
    # owner's role); otherwise it falls back to database_url.
    migration_database_url: str | None = None
    # Connection pool for each process (API and worker each have their own). Checked before use so
    # a connection the server dropped is replaced instead of failing the request, and recycled
    # well inside the idle limits of hosted databases.
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800
    db_connect_timeout_seconds: int = 10
    # Server-side limits on a single SQL statement and on waiting for a lock (0 = no limit). The
    # worker gets longer ones because its batch jobs run bigger statements; a model call is not a
    # statement, so these never cut a slow LLM call short.
    db_statement_timeout_ms: int = 30_000
    db_lock_timeout_ms: int = 15_000
    db_worker_statement_timeout_ms: int = 300_000
    db_worker_lock_timeout_ms: int = 60_000
    # A migration waits at most this long for a lock, so it fails fast instead of queueing behind
    # (and blocking) the running app.
    db_migration_lock_timeout_ms: int = 10_000
    # Shown in pg_stat_activity as "<name>-api", "<name>-worker", "<name>-migrations".
    db_application_name: str = "sales-intel"
    # "disable" locally; "require" or "verify-full" (with db_ssl_root_cert) on a hosted database.
    db_ssl_mode: Literal["disable", "require", "verify-full"] = "disable"
    db_ssl_root_cert: str | None = None

    gemini_api_key: str | None = None
    # A rolling alias, not a pinned version — each pinned free-tier model gets its own separate
    # small daily request quota (RESOURCE_EXHAUSTED, not a transient overload, once used up; see
    # gemini_client.py's quota-vs-overload distinction), so pinning to one specific model name
    # means every Gemini-backed feature in the app goes down together for the rest of the day
    # once that one model's quota is spent. The "latest" alias also means Google's own model
    # rollovers don't require a config change here.
    gemini_model: str = "gemini-flash-lite-latest"

    # Groq (https://console.groq.com) — OpenAI-compatible hosted models. Used through
    # modules/llm/structured.py, first by the offerings importer; unset key is a graceful state
    # (that vendor is skipped and the next one in the order answers).
    groq_api_key: str | None = None
    # Chosen from the models this account's key can actually list (GET /openai/v1/models).
    groq_model: str = "openai/gpt-oss-120b"
    groq_timeout_seconds: float = 30.0
    # A smaller, faster model for quick screening jobs (is this page worth reading?), so the
    # larger one is kept for writing the actual descriptions.
    groq_triage_model: str = "openai/gpt-oss-20b"

    # Offerings importer (modules/offerings): pulls InfoBeans' services and products from its
    # own website into a review queue. Each "order" is tried left to right, so either vendor can
    # be the primary and the other the fallback.
    offerings_llm_order: str = "groq,gemini"
    offerings_source_order: str = "contextdev,website"
    offerings_site_domain: str = "infobeans.ai"
    offerings_sitemap_url: str = "https://infobeans.ai/page-sitemap.xml"
    # Blog posts live in their own sitemap, mostly articles but with a few real offering pages
    # (Expona, Insane SDD). Posts are screened by a light model first; empty turns the lane off.
    offerings_post_sitemap_url: str = "https://infobeans.ai/post-sitemap.xml"
    offerings_triage_llm_order: str = "groq,gemini"
    # Pages that are always checked, even though they are not in the page sitemap.
    offerings_extra_urls: list[str] = []
    # The website menu is read each sync as an independent list of what the company itself puts
    # forward, to check the catalogue against. The named headings are the ones that hold offerings.
    offerings_menu_url: str = "https://infobeans.ai/"
    offerings_menu_groups: list[str] = ["Disciplines", "Innovation"]
    # Most blog-post finds read and suggested in one sync, so the first run cannot flood the review.
    offerings_max_post_suggestions: int = 25
    # A full re-read ignoring the sitemap's last-modified time, since that time can be bumped
    # site-wide or be wrong. 0 turns the periodic re-read off.
    offerings_full_recheck_days: int = 30
    # A page with no sitemap time to trust (an external menu link) is not re-read every sync,
    # only once this many days have passed.
    offerings_unknown_lastmod_days: int = 6
    # Pages that are never offerings (news, people, legal, events). Matched as path prefixes.
    offerings_exclude_paths: list[str] = [
        "/blog",
        "/podcasts",
        "/wow_podcast",
        "/true-stories",
        "/careers",
        "/current-openings",
        "/life-at-infobeans",
        "/investors",
        "/leadership",
        "/infobeans-foundation",
        "/contact-us",
        "/privacy-policy",
        "/disclaimer",
        "/testimonial",
        "/linkedin-feedback",
        "/ibf-registration",
        "/dreamforce",
        "/infobeans-knowledge",
        "/strategic-gold",
    ]
    # context.dev spend allowed for one sync (map 1 + about 1 per page), separate from the
    # per-run ceiling above so a sync can never use up a discovery run's budget.
    offerings_context_dev_max_credits: int = 150
    # How often the worker queues a sync on its own.
    offerings_sync_interval_days: int = 7

    scraper_user_agent: str = "SalesIntelligenceBot/0.1 (+internal tool)"
    scraper_request_delay_seconds: float = 1.0
    # Hard wall-clock ceilings. httpx's own timeout is per network read, so a server that
    # trickles bytes (observed: dhl.com) is never cut off and, in the serial job worker, would
    # stall a whole pipeline run. One request, and one company's whole scrape, are bounded here.
    scraper_hard_timeout_seconds: float = 20.0
    scraper_company_timeout_seconds: float = 45.0

    # context.dev (https://docs.context.dev) — brand/firmographics, news and JS-rendered page
    # scraping behind one API key. Evaluated on the feat/new-pipeline branch; see
    # docs/decisions/0012-context-dev-evaluation.md. Unset key is a valid, graceful state: the
    # factory falls back to the in-house scraper rather than erroring.
    context_dev_api_key: str | None = None
    context_dev_timeout_seconds: float = 30.0
    # Hard stop on context.dev spend within one run (jobs build their own provider, so this is a
    # per-run total). Once reached, further paid calls are skipped and the run carries on with
    # scraper data only. Estimated cost: brand 10, page scrape 1, news 1.
    context_dev_max_credits_per_run: int = 150
    # How many context.dev requests this process keeps in flight at once. The API limits an
    # organisation by concurrency and answers 429 above it, so calls queue here instead of failing.
    context_dev_max_concurrency: int = 2
    # Which source feeds company firmographics + signals in every enrichment path:
    #   scraper                          — in-house WebsiteScraperProvider only (the default)
    #   contextdev                       — context.dev only
    #   scraper_with_contextdev_fallback — scraper first; context.dev fills what it couldn't
    #                                      (industry, failed homepages) and adds news signals
    company_data_source: Literal["scraper", "contextdev", "scraper_with_contextdev_fallback"] = (
        "scraper"
    )

    # Google Custom Search JSON API — used only for domain discovery when a company has no
    # domain on file. Both unset is a valid, graceful state (GoogleCustomSearchProvider just
    # returns no match rather than erroring), so local dev works without a key.
    google_search_api_key: str | None = None
    google_search_engine_id: str | None = None

    # Serper.dev — wraps real Google SERP results, free tier (no card required). Default
    # discovery backend for both domain lookup (2a) and candidate discovery (2c), since Google
    # Custom Search no longer supports whole-web search on newly created engines.
    serper_api_key: str | None = None

    # Record every model call, search query and context.dev credit in `api_usage`, so cost is
    # measured. Turning it off only stops the recording; nothing else depends on it.
    usage_logging_enabled: bool = True

    # Language models for opportunity research, tried in this order. Gemini first: the judgment
    # needs a stronger model than the importer's small calls, and Groq's free per-minute token
    # limit is easily exceeded by a long evidence prompt.
    opportunity_llm_order: str = "gemini,groq"
    # Privacy switch for the structured-output seam. Groq may receive personal data (names, emails)
    # only after InfoBeans security has confirmed its terms; until then a chain built for
    # personal data skips it. Gemini is allowed (use a paid key, whose terms do not train on input).
    groq_may_receive_personal_data: bool = False

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

    # In-house search-based contact discovery (enrichment/providers/search_contacts.py) — reuses
    # SerperSearchProvider.search_raw, already paid-for infra, rather than a new vendor. Reads
    # only what a search engine already indexed about a trusted domain (never fetches/scrapes the
    # domain itself) — deliberately NOT a freeform user-edited query string, so the site scope
    # stays a controlled, reviewable allowlist rather than something a rep can widen by accident.
    contact_search_trusted_domains: list[str] = ["linkedin.com"]
    contact_search_enabled: bool = True  # off skips the extra Serper call entirely
    # A search-found person scoring below `min` is dropped (company association not established
    # strongly enough); between min and `likely` is kept but flagged low-confidence.
    contact_confidence_min: float = 0.6
    contact_confidence_likely: float = 0.8

    # One-Prompt Pipeline Orchestration (orchestrator/service.py). Safety cap on how many
    # qualified companies get carried through to role-classification and drafting in one
    # automatic run — protects the shared Gemini free-tier daily quota from one broad market
    # prompt exhausting it. Discovery and qualification themselves still process everything
    # found; only these two later, more Gemini-call-heavy stages are capped.
    auto_pipeline_max_companies_to_draft: int = 5
    # After ranking, the offerings a run was about are researched for real (area evidence, findings,
    # fit) so the Brief opens with an answer. Each company and offering is several model and search
    # calls, so both are capped: the top companies by score, and the first few offerings of the run.
    # Companies past the cap show "not checked yet" with a button instead.
    run_area_research_company_limit: int = 5
    run_area_research_offering_limit: int = 3

    # Phase C — Tracker & Cadence Mechanics (outreach/cadence.py). How many business days after a
    # "sent" outreach activity the next follow-up gets auto-scheduled, when not overridden.
    default_follow_up_gap_business_days: int = 3
    # IANA timezone name used for send-window math when a contact has no `timezone` of their own
    # set — most won't, initially, so this is the fallback, not a hard per-contact requirement.
    default_timezone: str = "UTC"

    # Phase 8b: the documents knowledge base (uploaded decks, PDFs, Word and Markdown files that
    # describe what we sell). Off until it is released (8f); the API answers 404 while it is off.
    documents_enabled: bool = False
    # No original file is kept: the upload sits in a staging row only until the background job has
    # read it, and a failed one is purged after this many hours (reprocess needs it until then).
    documents_staging_retention_hours: int = 24
    documents_max_upload_mb: int = 5
    # A file past these is refused with a clear message instead of tying the worker up.
    documents_max_pages: int = 300
    documents_max_chunks: int = 3000
    # A zip-based file (pptx, docx) may not unpack to more than this: a zip bomb is tiny on disk.
    documents_max_unpacked_mb: int = 200
    # Chunks: slide- and page-aware, about this long, with a little overlap when one is split.
    documents_chunk_chars: int = 1000
    documents_chunk_max_chars: int = 1400  # a slide or section up to this stays whole
    documents_chunk_overlap_chars: int = 150
    # Images, charts, unparseable tables and scanned pages can be described by a model (Gemini
    # vision). Off by default: it spends Gemini quota. A document with no images needs nothing.
    documents_vision_enabled: bool = False
    documents_vision_max_images: int = 40  # per document; the rest are listed as skipped
    documents_vision_concurrency: int = 3
    documents_vision_min_px: int = 50  # smaller images are icons, not content
    documents_vision_max_banner_ratio: float = 5.0  # wider than this x its height is a banner
    # Phase 8c: passages get a vector (Gemini embeddings) so search finds them by meaning as well
    # as by words. Off by default: it spends Gemini quota. While off, search still works by words.
    documents_embeddings_enabled: bool = False
    documents_embedding_model: str = "gemini-embedding-001"
    documents_embedding_batch: int = 20  # passages per request (free tier counts tokens per minute)
    documents_embedding_rate_wait_seconds: int = 65  # pause after a per-minute limit, then retry
    documents_search_candidates: int = 30  # taken from each of meaning and words before merging
    documents_search_max_results: int = 20
    # A passage found only by meaning is dropped when it is less similar to the question than this
    # (0 to 1, cosine). 0 keeps everything. Not calibrated yet: see the scores in the search box.
    documents_min_similarity: float = 0.0
    # Phase 8d: passages from the documents given to the fit and recommendation prompts. 0 turns it
    # off. Prompts with passages go to Gemini only (G1), never to a fallback vendor.
    documents_knowledge_passages: int = 5
    documents_knowledge_max_chars: int = 4000


@lru_cache
def get_settings() -> Settings:
    return Settings()
