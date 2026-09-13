# ADR 0001: Data Sourcing Strategy

**Status:** accepted
**Date:** 2026-08-31

## Context

Company/contact discovery data can be bought from paid providers (Apollo, Clay, Hunter,
PhantomBuster, Bright Data, etc.) or gathered in-house via scraping. This choice significantly
affects cost, legal exposure, and reliability. The in-house sales team this product supports
already works this way manually — surfing the web, gathering info, then reaching out — so the
product should automate that same free-sources approach rather than introduce a paid-data
dependency at PoC stage.

## Decision

Default to in-house scraping of free/public sources: company websites, public web search,
business directories, news/press pages. Prioritize data freshness. Honor `robots.txt`, rate
limits, and avoid bypassing logins/paywalls.

**LinkedIn is explicitly excluded from automated scraping for now.** LinkedIn's ToS prohibits
automated scraping and the legal landscape (despite popular belief) is not settled in scrapers'
favor. Company-website and public-web sources already cover most firmographic data and a good
share of decision-maker identification. LinkedIn is a separate, deliberate decision to revisit
later — not something to back into by default.

The `enrichment/providers/` interface abstracts this so a paid provider can be added later
without a rewrite.

## Consequences

- No paid data-provider cost at this stage.
- Data coverage/quality depends entirely on what's discoverable from public web sources — may be
  thinner than a paid provider for some firmographic fields (e.g. precise employee counts,
  funding data). Acceptable tradeoff for PoC validation.
- Revisit if: coverage proves insufficient, or if LinkedIn data becomes a hard product
  requirement (would need explicit legal review at that point, not an engineering-only decision).
