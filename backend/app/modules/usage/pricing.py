"""Estimated cost of a call, from published prices. These are estimates for budgeting, not a
bill: free tiers cost nothing but are metered the same way so the paid-equivalent is visible.

Sources (read 2026-10-28): the Google Gemini API pricing page (latest Flash-Lite, paid tier),
Serper's Starter plan ($50 per 50,000 queries) and context.dev's Developer plan overage ($3 per
1,000 credits). Groq's model prices were not found on its pricing page, so Groq calls record
tokens but no cost."""

# USD per 1M tokens: (input, output). The Gemini model used is the rolling Flash-Lite alias, so
# the current Flash-Lite price is used; thinking tokens are billed as output.
_LLM_PRICES_PER_MILLION: dict[str, tuple[float, float]] = {
    "gemini": (0.30, 2.50),
}

SERPER_USD_PER_QUERY = 0.001
CONTEXTDEV_USD_PER_CREDIT = 0.003


def estimate_cost_usd(
    provider: str, kind: str, tokens_in: int | None, tokens_out: int | None, units: int | None
) -> float | None:
    if kind == "llm":
        price = _LLM_PRICES_PER_MILLION.get(provider)
        if price is None or (tokens_in is None and tokens_out is None):
            return None
        return ((tokens_in or 0) * price[0] + (tokens_out or 0) * price[1]) / 1_000_000
    if kind == "search" and provider == "serper":
        return (units or 0) * SERPER_USD_PER_QUERY
    if kind == "credits" and provider == "contextdev":
        return (units or 0) * CONTEXTDEV_USD_PER_CREDIT
    return None
