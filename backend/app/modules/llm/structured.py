"""A small, vendor-neutral "give me this Pydantic model" call with ordered fallback.

Gemini is called directly from many places in the app; this seam exists so new features (first:
the offerings importer) can try Groq first and fall back to Gemini — or the other way round —
without each feature knowing which vendor answered. Groq is spoken to over its OpenAI-compatible
HTTP API with `httpx`, so it adds no dependency."""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import TypeVar

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.modules.ai_recommendation.gemini_client import (
    format_gemini_error,
    generate_content_with_retry,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# Groq's free tier limits tokens per minute, so back-to-back calls get 429 with a Retry-After.
# A short wait usually clears it; anything longer falls through to the next vendor instead.
_GROQ_MAX_WAIT_SECONDS = 20.0
_GROQ_ATTEMPTS = 2


class LLMError(RuntimeError):
    """This vendor could not give a valid answer (not configured, rate limited, bad output). The
    fallback chain treats it as "try the next one", never as a crash."""


class StructuredLLM(ABC):
    name: str

    @abstractmethod
    async def generate(self, prompt: str, schema: type[T]) -> T: ...


class GroqStructuredLLM(StructuredLLM):
    name = "groq"

    def __init__(self, settings: Settings, model: str | None = None) -> None:
        self._api_key = settings.groq_api_key
        self._model = model or settings.groq_model
        self._timeout = settings.groq_timeout_seconds

    async def generate(self, prompt: str, schema: type[T]) -> T:
        if not self._api_key:
            raise LLMError("GROQ_API_KEY is not configured")
        # JSON mode needs the word "JSON" in the prompt and does not enforce a schema, so the
        # schema is spelled out in the prompt and the reply is validated against it afterwards.
        full_prompt = (
            f"{prompt}\n\nReply with a single JSON object that matches this JSON schema, and "
            f"nothing else:\n{json.dumps(schema.model_json_schema())}"
        )
        body = {
            "model": self._model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": full_prompt}],
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            for attempt in range(_GROQ_ATTEMPTS):
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(_GROQ_URL, headers=headers, json=body)
                wait = _retry_after_seconds(resp)
                if resp.status_code == 429 and attempt + 1 < _GROQ_ATTEMPTS and wait is not None:
                    await asyncio.sleep(wait)
                    continue
                break
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return schema.model_validate_json(content)
        except httpx.HTTPStatusError as exc:
            raise LLMError(f"Groq request failed ({exc.response.status_code})") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach Groq: {exc}") from exc
        except (KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
            raise LLMError(f"Groq did not return a valid answer: {exc}") from exc


def _retry_after_seconds(resp: httpx.Response) -> float | None:
    """How long Groq asks us to wait, when that is short enough to be worth waiting for."""
    try:
        seconds = float(resp.headers.get("retry-after", ""))
    except ValueError:
        return None
    return seconds if 0 <= seconds <= _GROQ_MAX_WAIT_SECONDS else None


class GeminiStructuredLLM(StructuredLLM):
    name = "gemini"

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.gemini_api_key
        self._model = settings.gemini_model

    async def generate(self, prompt: str, schema: type[T]) -> T:
        if not self._api_key:
            raise LLMError("GEMINI_API_KEY is not configured")
        client = genai.Client(api_key=self._api_key)
        try:
            response = await generate_content_with_retry(
                client,
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0,
                ),
            )
        except genai_errors.APIError as exc:
            raise LLMError(format_gemini_error(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - reported as "this vendor failed", chain moves on
            raise LLMError(f"Gemini request failed: {exc}") from exc
        parsed = response.parsed
        if not isinstance(parsed, schema):
            raise LLMError("Gemini did not return a valid structured response")
        return parsed


class FallbackStructuredLLM(StructuredLLM):
    """Tries each vendor in order and returns the first valid answer, remembering which ones
    answered (`used`) so a run can report it."""

    name = "fallback"

    def __init__(self, vendors: list[StructuredLLM]) -> None:
        self._vendors = vendors
        self.used: set[str] = set()

    async def generate(self, prompt: str, schema: type[T]) -> T:
        errors: list[str] = []
        for vendor in self._vendors:
            try:
                result = await vendor.generate(prompt, schema)
            except LLMError as exc:
                logger.info("%s could not answer, trying the next: %s", vendor.name, exc)
                errors.append(f"{vendor.name}: {exc}")
                continue
            self.used.add(vendor.name)
            return result
        raise LLMError("; ".join(errors) or "no language model is configured")


def build_structured_llm(
    settings: Settings, order: str | None = None, groq_model: str | None = None
) -> FallbackStructuredLLM:
    """`order` is a comma list such as "groq,gemini"; unknown names are ignored. `groq_model`
    swaps in a different Groq model (the light screening one) for this chain."""
    names = [n.strip().lower() for n in (order or settings.offerings_llm_order).split(",")]
    vendors: list[StructuredLLM] = []
    for name in names:
        if name == "groq":
            vendors.append(GroqStructuredLLM(settings, groq_model))
        elif name == "gemini":
            vendors.append(GeminiStructuredLLM(settings))
    return FallbackStructuredLLM(vendors)
