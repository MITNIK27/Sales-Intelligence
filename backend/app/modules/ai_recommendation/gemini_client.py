"""Thin, swappable Gemini client (per ADR 0002) — Market Discovery (Phase 2c) is its first
consumer; Phase 3's pitch-recommendation layer will reuse it later."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.config import Settings
from app.modules.usage.recorder import elapsed_ms, record_usage, short_error, started

Confidence = Literal["confident", "could_not_determine"]

# Google's own free-tier models routinely return transient 503 (model overloaded) or 429 (rate
# limited) errors — genuinely temporary, not a config/code problem. Retrying a couple of times
# with backoff turns a one-off blip into a working call instead of an immediate user-facing
# failure, per the "retries with backoff at the abstraction boundary" cross-cutting concern in
# the foundational plan (never implemented until this was hit in live testing).
_RETRYABLE_STATUS_CODES = {429, 503}

# A dropped/refused connection ("All connection attempts failed", a read timeout, a reset) is the
# same kind of transient: Wi-Fi or VPN flickering, a dual-stack IPv6 route failing for a moment.
# It used to fail the whole job instantly because only Google's own 429/503 were retried — a
# single blip lost a discovery run mid-pipeline. Module constants so tests can zero the waits.
_RETRY_ATTEMPTS = 4
_RETRY_WAIT_MULTIPLIER = 2.0
_RETRY_WAIT_MIN = 2.0
_RETRY_WAIT_MAX = 15.0


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
    violations = details.get("error", {}).get("details", []) if isinstance(details, dict) else []
    for detail in violations:
        for violation in detail.get("violations", []):
            if "PerDay" in violation.get("quotaId", ""):
                return True
    return False


def _is_retryable_gemini_error(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True  # connection never opened / dropped mid-flight: worth another try
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


async def _generate_metered(client: genai.Client, **kwargs: Any) -> types.GenerateContentResponse:
    """One attempt, recorded in the usage log: tokens when it succeeded, an error row when it did
    not. Every retry is its own attempt, so retries show up in the counts."""
    begin = started()
    model = kwargs.get("model")
    try:
        response = await client.aio.models.generate_content(**kwargs)
    except Exception as exc:
        await record_usage(
            provider="gemini",
            kind="llm",
            status="error",
            model=model,
            latency_ms=elapsed_ms(begin),
            error=short_error(exc),
        )
        raise
    usage = getattr(response, "usage_metadata", None)
    # Thinking tokens are billed as output, so they are counted with it (and shown separately).
    thinking = getattr(usage, "thoughts_token_count", None)
    out = (getattr(usage, "candidates_token_count", None) or 0) + (thinking or 0)
    await record_usage(
        provider="gemini",
        kind="llm",
        model=model,
        tokens_in=getattr(usage, "prompt_token_count", None),
        tokens_out=out if usage is not None else None,
        cached_tokens=getattr(usage, "cached_content_token_count", None),
        thinking_tokens=thinking,
        latency_ms=elapsed_ms(begin),
    )
    return response


async def generate_content_with_retry(
    client: genai.Client, **kwargs: Any
) -> types.GenerateContentResponse:
    """Shared call path for both Gemini consumers (Market Discovery parsing, Recommendation
    generation) — retries transient overload/rate-limit errors, lets everything else (bad
    request, auth failure, malformed schema) fail immediately since retrying those never helps."""
    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(_RETRY_ATTEMPTS),
            wait=wait_exponential(
                multiplier=_RETRY_WAIT_MULTIPLIER, min=_RETRY_WAIT_MIN, max=_RETRY_WAIT_MAX
            ),
            retry=retry_if_exception(_is_retryable_gemini_error),
            reraise=True,
        ):
            with attempt:
                return await _generate_metered(client, **kwargs)
    except httpx.TransportError as exc:
        raise GeminiClientError(
            f"Could not reach Gemini after {_RETRY_ATTEMPTS} tries — this is a network problem "
            f"on this machine, not a Gemini or configuration problem. Check the internet/VPN "
            f"connection and try again. ({exc})"
        ) from exc
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


class GeminiRateLimitedError(GeminiClientError):
    """A per-minute limit was reached (not the daily allowance): waiting a minute fixes it."""


class GeminiInvalidResponseError(GeminiClientError):
    """Gemini answered, but the answer could not be read as the requested schema (even after the
    one repair try), or was cut off at the output cap."""


# The cap on a reply's length (thinking tokens count towards it). Far above any answer this app
# asks for, so it never cuts a real answer short; it only stops a runaway reply from being billed
# without limit. Passed explicitly at every call so the choice is visible where the call is made.
MAX_OUTPUT_TOKENS = 8192

_REPAIR_NOTE = (
    "\n\nYour previous reply could not be read as the required JSON. Reply again with only the "
    "JSON object that matches the schema."
)


def _hit_output_limit(response: types.GenerateContentResponse) -> bool:
    candidates = getattr(response, "candidates", None) or []
    reason = getattr(candidates[0], "finish_reason", None) if candidates else None
    return reason is not None and getattr(reason, "name", str(reason)) == "MAX_TOKENS"


async def generate_structured[T: BaseModel](
    *,
    api_key: str,
    model: str,
    prompt: str,
    schema: type[T],
    temperature: float | None,
    max_output_tokens: int,
    thinking_budget: int | None = None,
) -> T:
    """The one place the app asks Gemini for a structured answer (docs/ai-governance.md, G6).

    `temperature=None` leaves the provider default; it is a required argument so each caller
    records its choice. `thinking_budget` is only sent when given: not every Gemini model accepts
    every budget (some cannot switch thinking off), so it is not forced on all calls.

    A reply that is not valid for the schema gets one more try with a short note appended (G7),
    unless it was cut off at the output cap, where asking again would only cut it off again.
    Every failure is raised as `GeminiClientError`; callers that report another error type
    translate it."""
    client = genai.Client(api_key=api_key)
    config_args: dict[str, Any] = {
        "response_mime_type": "application/json",
        "response_schema": schema,
        "max_output_tokens": max_output_tokens,
    }
    if temperature is not None:
        config_args["temperature"] = temperature
    if thinking_budget is not None:
        config_args["thinking_config"] = types.ThinkingConfig(thinking_budget=thinking_budget)
    config = types.GenerateContentConfig(**config_args)

    for attempt in (1, 2):
        try:
            response = await generate_content_with_retry(
                client,
                model=model,
                contents=prompt if attempt == 1 else prompt + _REPAIR_NOTE,
                config=config,
            )
        except GeminiClientError:
            raise
        except genai_errors.APIError as exc:
            raise GeminiClientError(format_gemini_error(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller as a clear failure
            raise GeminiClientError(f"Gemini request failed: {exc}") from exc

        parsed = response.parsed
        if isinstance(parsed, schema):
            return parsed
        if _hit_output_limit(response):
            raise GeminiInvalidResponseError(
                f"Gemini did not return a valid structured response: the answer was cut off at "
                f"{max_output_tokens} tokens"
            )
    raise GeminiInvalidResponseError("Gemini did not return a valid structured response")


@dataclass(frozen=True)
class VisionResult:
    text: str
    model: str
    tokens_in: int | None
    tokens_out: int | None


async def describe_image(
    *,
    api_key: str,
    model: str,
    prompt: str,
    png: bytes,
    temperature: float | None,
    max_output_tokens: int,
) -> VisionResult:
    """The one place the app sends a picture to Gemini (docs/ai-governance.md, G6), beside
    `generate_structured` so it shares the retry, the usage log and the error handling. The answer
    is plain text (a description, a Markdown table or a page transcription), not a schema.

    A reply that was cut off at the output cap is an error, not a quietly shortened answer."""
    client = genai.Client(api_key=api_key)
    config_args: dict[str, Any] = {"max_output_tokens": max_output_tokens}
    if temperature is not None:
        config_args["temperature"] = temperature
    try:
        response = await generate_content_with_retry(
            client,
            model=model,
            contents=[types.Part.from_bytes(data=png, mime_type="image/png"), prompt],
            config=types.GenerateContentConfig(**config_args),
        )
    except GeminiClientError:
        raise
    except genai_errors.APIError as exc:
        raise GeminiClientError(format_gemini_error(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller as a clear failure
        raise GeminiClientError(f"Gemini request failed: {exc}") from exc

    if _hit_output_limit(response):
        raise GeminiInvalidResponseError(
            f"Gemini's description was cut off at {max_output_tokens} tokens"
        )
    try:
        text = (response.text or "").strip()
    except Exception:  # noqa: BLE001 - no candidates (blocked or empty reply)
        text = ""
    if not text:
        raise GeminiInvalidResponseError("Gemini returned no description for this picture")
    usage = getattr(response, "usage_metadata", None)
    thinking = getattr(usage, "thoughts_token_count", None) or 0
    out = (getattr(usage, "candidates_token_count", None) or 0) + thinking
    return VisionResult(
        text=text,
        model=model,
        tokens_in=getattr(usage, "prompt_token_count", None),
        tokens_out=out if usage is not None else None,
    )


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model: str
    tokens_in: int  # estimated: the Developer API does not report it for embeddings


def _normalised(vector: list[float]) -> list[float]:
    """Unit length. Gemini embeddings cut to fewer than 3072 dimensions are not normalised, and
    cosine comparison (and the index) assume they are, so it is done here once."""
    norm = sum(x * x for x in vector) ** 0.5
    return [x / norm for x in vector] if norm else vector


async def embed_texts(
    *,
    api_key: str,
    model: str,
    texts: list[str],
    task: Literal["document", "query"],
    dimensions: int,
) -> EmbeddingResult:
    """The one place the app turns text into vectors (docs/ai-governance.md, G6), beside
    `generate_structured`. Passages are embedded as documents and a search question as a query: the
    model places the two kinds so that a question lands near the passages that answer it. One
    attempt is recorded per request in the usage log, retries included."""
    client = genai.Client(api_key=api_key)
    config = types.EmbedContentConfig(
        task_type="RETRIEVAL_DOCUMENT" if task == "document" else "RETRIEVAL_QUERY",
        output_dimensionality=dimensions,
    )
    est_tokens = sum(len(t) for t in texts) // 4 + len(texts)
    contents: Any = list(texts)
    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(_RETRY_ATTEMPTS),
            wait=wait_exponential(
                multiplier=_RETRY_WAIT_MULTIPLIER, min=_RETRY_WAIT_MIN, max=_RETRY_WAIT_MAX
            ),
            retry=retry_if_exception(_is_retryable_gemini_error),
            reraise=True,
        ):
            with attempt:
                begin = started()
                try:
                    response = await client.aio.models.embed_content(
                        model=model, contents=contents, config=config
                    )
                except Exception as exc:
                    await record_usage(
                        provider="gemini",
                        kind="embedding",
                        status="error",
                        model=model,
                        units=len(texts),
                        latency_ms=elapsed_ms(begin),
                        error=short_error(exc),
                    )
                    raise
                await record_usage(
                    provider="gemini",
                    kind="embedding",
                    model=model,
                    tokens_in=est_tokens,
                    units=len(texts),
                    latency_ms=elapsed_ms(begin),
                )
    except httpx.TransportError as exc:
        raise GeminiClientError(f"Could not reach Gemini: {exc}") from exc
    except genai_errors.APIError as exc:
        if exc.code == 429 and not _is_quota_exhausted(exc):
            raise GeminiRateLimitedError(
                "Gemini's per-minute limit for embeddings was reached (requests or tokens per "
                "minute); it clears after a short wait."
            ) from exc
        raise GeminiClientError(format_gemini_error(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller as a clear failure
        raise GeminiClientError(f"Gemini request failed: {exc}") from exc

    vectors = [list(e.values or []) for e in (response.embeddings or [])]
    if len(vectors) != len(texts) or any(len(v) != dimensions for v in vectors):
        raise GeminiInvalidResponseError("Gemini returned embeddings of an unexpected shape")
    return EmbeddingResult(
        vectors=[_normalised(v) for v in vectors], model=model, tokens_in=est_tokens
    )


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

        return await generate_structured(
            api_key=self._settings.gemini_api_key,
            model=self._settings.gemini_model,
            prompt=_PROMPT_TEMPLATE.format(raw_text=raw_text),
            schema=MarketCriteria,
            temperature=None,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
