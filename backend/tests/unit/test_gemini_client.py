import pytest
from google.genai import errors as genai_errors

from app.core.config import Settings
from app.modules.ai_recommendation.gemini_client import (
    GeminiClientError,
    GeminiMarketDescriptionParser,
    _is_retryable_gemini_error,
    format_gemini_error,
)


async def test_parse_raises_clear_error_without_api_key() -> None:
    parser = GeminiMarketDescriptionParser(Settings(gemini_api_key=None))
    with pytest.raises(GeminiClientError, match="GEMINI_API_KEY"):
        await parser.parse("SaaS companies in Bangalore, 50-200 employees")


def _quota_exhausted_error() -> genai_errors.APIError:
    """Shaped like Google's real response for a spent free-tier daily-per-model quota — captured
    live when this exact error was misreported as a transient overload for over an hour."""
    response_json = {
        "error": {
            "code": 429,
            "status": "RESOURCE_EXHAUSTED",
            "message": "You exceeded your current quota...",
            "details": [
                {
                    "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                    "violations": [
                        {
                            "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                        }
                    ],
                }
            ],
        }
    }
    return genai_errors.APIError(429, response_json)


def _rate_limited_error() -> genai_errors.APIError:
    """A genuinely transient per-minute rate limit, not a spent daily quota — no QuotaFailure
    detail carrying a "PerDay" quotaId."""
    return genai_errors.APIError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}})


def _overloaded_error() -> genai_errors.APIError:
    return genai_errors.APIError(503, {"error": {"code": 503, "status": "UNAVAILABLE"}})


def test_quota_exhausted_error_is_not_retryable() -> None:
    assert _is_retryable_gemini_error(_quota_exhausted_error()) is False


def test_quota_exhausted_error_message_names_the_real_cause() -> None:
    message = format_gemini_error(_quota_exhausted_error())
    assert "daily request quota is used up" in message
    assert "GEMINI_MODEL" in message


def test_rate_limited_and_overloaded_errors_are_still_retryable() -> None:
    assert _is_retryable_gemini_error(_rate_limited_error()) is True
    assert _is_retryable_gemini_error(_overloaded_error()) is True
    assert "temporarily overloaded" in format_gemini_error(_rate_limited_error())
