# ADR 0011: LinkedIn / Gmail Integration Scope

**Status:** proposed
**Date:** 2026-09-23

## Context

Raised directly: could connecting a rep's own LinkedIn and/or Gmail account improve results —
better contact accuracy, and actually sending outreach instead of manually logging it? Today
neither exists. Contact discovery is the website scraper plus the in-house search-based technique
from ADR 0010 (Serper snippets that look like LinkedIn profiles, never a direct LinkedIn request);
ADR 0001 already ruled out scraping LinkedIn directly on ToS/account-ban grounds, and ADR 0010's
own "deferred" section flagged a rep linking their own LinkedIn account as a real but separate,
larger idea. "Log as Sent" (Phase B/C) is a manual rep action — a `Draft` is marked sent by the rep
after they've actually sent it themselves elsewhere; nothing in this app sends email today.

This ADR doesn't build either integration. It records the decision on how to prioritize them, so
the choice is deliberate rather than silently deferred a second time.

## Decision

1. **Do not connect a rep's personal LinkedIn account**, now or as a near-term next step. This
   reaffirms ADR 0001: automated access to LinkedIn under a real account risks that account being
   banned, and scraping/automating LinkedIn is against its ToS regardless of whose credentials are
   used. If contact-finding accuracy needs to materially improve beyond what the website scraper +
   ADR 0010's search technique provide, the correct next step is evaluating a paid enrichment
   vendor (Apollo.io / Hunter.io — both already researched as viable in ADR 0010's own deferred
   section), not a personal LinkedIn connection.

2. **Gmail send integration is the higher-value, lower-risk candidate for the next integration
   phase** — not built in this pass, but recommended as what to scope next when integration work
   resumes. Turning "Log as Sent" from a manual rep action into a real OAuth2 + Gmail API send
   would: (a) remove the one remaining manual step in the otherwise-automated draft-to-send flow,
   and (b) let `OutreachActivity` capture a real Gmail thread/message id, which opens the door to
   detecting replies automatically instead of a rep manually logging `response_received` — closing
   a loop the Phase C tracker/cadence mechanics currently assume a human does by hand.

3. **Scope, if/when Gmail send is taken up**: per-rep OAuth2 (each rep authorizes their own Gmail,
   not a shared service account — outreach must appear to come from the rep, matching how the
   tracker already models one rep's personal follow-up cadence), token storage/refresh, sending via
   the Gmail API rather than SMTP (avoids handling raw credentials), and a decision on whether reply
   detection is polling-based or push (Gmail watch/webhook) — left open for that future scoping
   pass, not decided here.

## Consequences

- No new integration work happens as part of this ADR — it exists to make the prioritization
  explicit: Gmail send before LinkedIn connection, and vendor enrichment (if pursued) before either.
- Nothing about the current contact-discovery or draft/send flow changes; reps continue searching
  for contacts via the existing heuristics and logging sends manually until a future pass
  implements Gmail send.
- Revisit when: enrichment quality genuinely blocks reps (favor evaluating a paid vendor first), or
  when reducing the manual "Log as Sent" step and enabling reply auto-detection becomes a priority
  (favor Gmail send).
