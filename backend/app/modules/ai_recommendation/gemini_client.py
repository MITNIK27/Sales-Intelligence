"""Thin, swappable Gemini client (per ADR 0002) — Market Discovery (Phase 2c) is its first
consumer; Phase 3's pitch-recommendation layer will reuse it later."""

from abc import ABC, abstractmethod
from typing import Any, Literal

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.config import Settings

Confidence = Literal["confident", "could_not_determine"]

# Google's own free-tier models routinely return transient 503 (model overloaded) or 429 (rate
# limited) errors — genuinely temporary, not a config/code problem. Retrying a couple of times
# with backoff turns a one-off blip into a working call instead of an immediate user-facing
# failure, per the "retries with backoff at the abstraction boundary" cross-cutting concern in
# the foundational plan (never implemented until this was hit in live testing).
_RETRYABLE_STATUS_CODES = {429, 503}


def _is_quota_exhausted(exc: genai_errors.APIError) -> bool:
    """A 429 can mean two very different things: a short per-minute rate limit (genuinely
    transient, worth retrying) or the free tier's small per-day-per-model request quota being
    used up entirely (RESOURCE_EXHAUSTED with a "PerDay" quota id) — which will not clear for
    hours no matter how many times it's retried. Learned live: this got misreported as "Gemini
    is temporarily overloaded, try again in a moment" for over an hour when it was actually a
    spent daily quota on one specific model name."""
    if exc.code != 429 or exc.status != "RESOURCE_EXHAUSTED":
        return False
    details = exc.details if isinstance(exc.details, dict) else {}
    violations = (
        details.get("error", {}).get("details", []) if isinstance(details, dict) else []
    )
    for detail in violations:
        for violation in detail.get("violations", []):
            if "PerDay" in violation.get("quotaId", ""):
                return True
    return False


def _is_retryable_gemini_error(exc: BaseException) -> bool:
    if not isinstance(exc, genai_errors.APIError):
        return False
    if _is_quota_exhausted(exc):
        return False  # retrying can't help — the daily allowance is gone until Google resets it
    return exc.code in _RETRYABLE_STATUS_CODES


def format_gemini_error(exc: genai_errors.APIError) -> str:
    """A human-readable message instead of the raw response dict — this is what a user sees
    in the UI, so it should read as prose, not a stack trace."""
    if _is_quota_exhausted(exc):
        return (
            "This Gemini model's free-tier daily request quota is used up — this will not "
            "clear by retrying; it resets on Google's daily schedule. Switch GEMINI_MODEL to a "
            "different free-tier model (each has its own separate daily quota) to unblock "
            f"immediately. ({exc.message})"
        )
    if exc.code in _RETRYABLE_STATUS_CODES:
        return (
            "Gemini is temporarily overloaded (tried 3 times) — this is a transient issue on "
            "Google's side, not a configuration problem. Please try again in a moment."
        )
    return f"Gemini request failed ({exc.code} {exc.status}): {exc.message}"


async def generate_content_with_retry(
    client: genai.Client, **kwargs: Any
) -> types.GenerateContentResponse:
    """Shared call path for both Gemini consumers (Market Discovery parsing, Recommendation
    generation) — retries transient overload/rate-limit errors, lets everything else (bad
    request, auth failure, malformed schema) fail immediately since retrying those never helps."""
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception(_is_retryable_gemini_error),
        reraise=True,
    ):
        with attempt:
            return await client.aio.models.generate_content(**kwargs)
    raise AssertionError("unreachable — AsyncRetrying always returns or raises")


class ParsedListField(BaseModel):
    value: list[str]
    confidence: Confidence


class ParsedOptionalStrField(BaseModel):
    value: str | None
    confidence: Confidence


class MarketCriteria(BaseModel):
    industry_keywords: ParsedListField
    location: ParsedOptionalStrField
    employee_size_range: ParsedOptionalStrField


class GeminiClientError(RuntimeError):
    """Raised when the Gemini API can't be called or doesn't return a valid structured
    response. Unlike the search/domain-discovery providers, there's nothing useful to fall
    back to here — the caller must surface this, not silently continue."""


_PROMPT_TEMPLATE = """You are parsing a sales rep's free-text description of a target market \
into structured search criteria. Extract exactly these three fields:

- industry_keywords: short keywords/phrases describing the industry or business type (e.g. \
["SaaS", "fintech"]). Empty list if none can be determined.
- location: a city, region, or country. null if none is mentioned.
- employee_size_range: a headcount range as free text (e.g. "50-200", "11-50"). null if none \
is mentioned.

For each field, set confidence to "confident" only if the text clearly states it. If you would \
be guessing, set confidence to "could_not_determine" and leave the value empty/null — never \
invent a value that isn't supported by the text.

Text to parse:
\"\"\"{raw_text}\"\"\"
"""


class MarketDescriptionParser(ABC):
    @abstractmethod
    async def parse(self, raw_text: str) -> MarketCriteria: ...


class GeminiMarketDescriptionParser(MarketDescriptionParser):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def parse(self, raw_text: str) -> MarketCriteria:
        if not self._settings.gemini_api_key:
            raise GeminiClientError("GEMINI_API_KEY is not configured")

        client = genai.Client(api_key=self._settings.gemini_api_key)
        try:
            response = await generate_content_with_retry(
                client,
                model=self._settings.gemini_model,
                contents=_PROMPT_TEMPLATE.format(raw_text=raw_text),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=MarketCriteria,
                ),
            )
        except genai_errors.APIError as exc:
            raise GeminiClientError(format_gemini_error(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller as a clear failure
            raise GeminiClientError(f"Gemini request failed: {exc}") from exc

        parsed = response.parsed
        if not isinstance(parsed, MarketCriteria):
            raise GeminiClientError("Gemini did not return a valid structured response")
        return parsed
