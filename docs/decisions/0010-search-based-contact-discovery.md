# ADR 0010: In-House Search-Based Contact Discovery

**Status:** accepted
**Date:** 2026-09-14

## Context

The website scraper (`WebsiteScraperProvider`) is the only contact source in the app — limited to
whatever a company's own `/about`/`/team`/`/leadership` pages happen to list. Many real
decision-makers are never mentioned there at all. ADR 0001 already ruled out scraping LinkedIn
directly (ToS risk, needs legal review to revisit) and this session separately researched paid
enrichment vendors (Apollo.io, Hunter.io — real options; Clearbit is no longer viable standalone,
folded into HubSpot's Breeze Intelligence) and deliberately deferred choosing one to its own pass.
This ADR covers a third option, built now: an in-house capability that searches a curated set of
trusted sites for public mentions of a company's people, reusing infrastructure this app already
has and already pays for.

## Decisions

1. **Reads search-engine-indexed snippets, never fetches the trusted sites themselves.**
   `SerperContactSearchProvider` calls `SerperSearchProvider.search_raw` (already built, already
   used for domain/candidate discovery) and only reads the `title`/`link`/`snippet` fields Google's
   own index already returns — it never issues a request to linkedin.com or any other trusted
   domain. This is a materially different, lower-risk technique than scraping the site directly,
   and is exactly what the discovery agent's own candidate search already does elsewhere in this
   codebase, just applied to people instead of companies.

2. **A configurable, curated domain allowlist — not a freeform query, and not the whole web.**
   `settings.contact_search_trusted_domains` (default `["linkedin.com"]`) scopes every search via
   `site:` filters. The search query itself is composed from this list plus the shared
   `DECISION_MAKER_KEYWORDS` vocabulary by a pure function (`build_contact_search_query`) —
   deliberately not an org-edited raw template string, so the site scope stays a reviewable,
   intentional list rather than something a rep could widen by accident (typo, scope creep) into
   searching untrusted sites.

3. **Both automatic and manual**, per explicit user direction: `_enrich_company` runs it
   automatically alongside the website scraper for every enrichment, and
   `POST /companies/{id}/search-contacts` lets a rep trigger it on demand for one company at will
   — fast enough (one search call + parsing) to stay synchronous, no job needed.

4. **Heuristic and low-confidence by nature — every result is reviewable, not authoritative.**
   `_parse_result` is a best-effort parse of a search result title (`"Name - Title - Company |
   LinkedIn"` and similar shapes) — meaningfully noisier than a company's own team page. Every
   contact found this way gets `needs_review=True`,
   `needs_review_reason="found via contact search, not confirmed"` (same pattern the app already
   uses for search-derived companies in Market Discovery). New: contact **deletion**
   (`delete_contact`) didn't exist anywhere before this — a rep can now remove a contact that
   turned out irrelevant (e.g. a scraped junior employee), the explicit review/removal step this
   capability's honesty requires. Deletion is refused (`ContactHasHistoryError`, 409) when the
   contact has existing `OutreachActivity`/`Draft` rows — those are deliberately append-only audit
   trails elsewhere in this codebase representing a real, deliberate rep action (a message
   actually sent, a draft actually generated for review), and deleting a contact with real history
   would silently destroy it. `RoleRelevanceResult` deliberately does **not** block deletion:
   classification runs automatically for every contact at a company the instant "Classify Roles"
   is clicked, with no human review involved — treating it as blocking would mean a rep could
   never clean up a bad lead after running the very classification step the app pushes them to run
   first. The history check is done explicitly in Python rather than relying on the database's own
   FK enforcement, since SQLite (used in tests) doesn't enforce foreign keys by default — an
   implicit DB-level check would behave differently in tests than in production.

5. **Dedup for free.** A search-found contact goes through the same `get_or_create_contact`
   (company_id, normalized name) matching every other contact source already uses — no separate
   dedup logic needed, and a person already found by the website scraper won't get a second row
   just because search also turned them up.

## Deferred, explicitly noted

- **A rep linking their own LinkedIn account** to make search/access easier — a real idea raised
  during this work, but a genuinely separate, larger piece (OAuth, session handling, per-rep
  credentials) with its own scope and risk profile. Not built now; revisit alongside ADR 0001's own
  "revisit later" framing if/when this becomes a priority.
- **Apollo.io / Hunter.io integration** — real, viable paid options (both have usable free tiers),
  deliberately not chosen or built here; cost + ADR 0001's legal-review flag make this its own
  pass, and this in-house capability may reduce how urgent that pass is.

## Consequences

- No new external vendor, no new cost — this reuses Serper calls the app already makes and pays
  for elsewhere.
- Result quality is inherently lower-confidence than on-site scraping; the `needs_review` flag and
  new delete capability are load-bearing here, not optional polish — without them this would be
  quietly shipping unreliable data as if it were verified.
- One additional Serper call per enrichment when `contact_search_enabled` is on (default) — a real
  but small, already-budgeted cost; `contact_search_enabled=false` is available if this needs to be
  turned off.
