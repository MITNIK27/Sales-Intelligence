// Plain-language explanations for the internal `needs_review_reason` strings written by the
// backend (enrichment/service.py, ingestion/market_discovery.py). The raw strings are
// identifiers, not copy meant for a rep to read verbatim — this maps the ones we know about to
// something that actually tells a rep what happened and what to check; anything unrecognized
// falls back to the raw reason rather than showing nothing.
const NEEDS_REVIEW_EXPLANATIONS: Record<string, string> = {
  "found via contact search, not confirmed":
    "Found by an automated web search, not verified by a person — confirm this contact's identity and title before reaching out.",
  "found via contact search, low confidence - check the company":
    "Found by a web search, but we are not sure this person works at this company — check before reaching out.",
  "found via contact search (likely match), not confirmed":
    "Found by a web search and likely works at this company, but not verified by a person — confirm before reaching out.",
  "found via Market Discovery search, not confirmed":
    "Found by an automated search while discovering this market, not manually verified — confirm the company details are accurate.",
  "domain found via search API, not confirmed":
    "This company's website was guessed by a search tool, not confirmed — check it's the right site before using it.",
  "no verified email found":
    "A contact was found, but no working email address could be confirmed for them.",
};

// The same reasons in two or three words, for a table cell; the full explanation goes on hover.
const SHORT_REASONS: Record<string, string> = {
  "found via contact search, not confirmed": "Found by web search",
  "found via contact search, low confidence - check the company":
    "Low confidence",
  "found via contact search (likely match), not confirmed": "Likely match",
  "found via Market Discovery search, not confirmed": "Found during discovery",
  "domain found via search API, not confirmed": "Website guessed",
  "no verified email found": "No verified email",
};

export function shortNeedsReviewReason(
  reason: string | null | undefined,
): string {
  if (!reason) return "Needs a check";
  return SHORT_REASONS[reason] ?? reason;
}

export function explainNeedsReviewReason(
  reason: string | null | undefined,
): string | null {
  if (!reason) return null;
  return NEEDS_REVIEW_EXPLANATIONS[reason] ?? reason;
}
