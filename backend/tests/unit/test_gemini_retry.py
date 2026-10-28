import httpx
import pytest

from app.modules.ai_recommendation import gemini_client
from app.modules.ai_recommendation.gemini_client import (
    GeminiClientError,
    generate_content_with_retry,
)


class _FlakyModels:
    def __init__(self, failures: int) -> None:
        self.calls = 0
        self._failures = failures

    async def generate_content(self, **kwargs: object) -> str:
        self.calls += 1
        if self.calls <= self._failures:
            raise httpx.ConnectError("All connection attempts failed")
        return "ok"


class _FakeClient:
    def __init__(self, failures: int) -> None:
        self.models = _FlakyModels(failures)
        self.aio = self  # client.aio.models.generate_content


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch) -> None:
    monkeypatch.setattr(gemini_client, "_RETRY_WAIT_MULTIPLIER", 0.0)
    monkeypatch.setattr(gemini_client, "_RETRY_WAIT_MIN", 0.0)


async def test_a_dropped_connection_is_retried_and_then_succeeds() -> None:
    client = _FakeClient(failures=2)
    result = await generate_content_with_retry(client, model="m", contents="x")  # type: ignore[arg-type]
    assert result == "ok"
    assert client.models.calls == 3


async def test_persistent_network_failure_raises_a_clear_error() -> None:
    client = _FakeClient(failures=99)
    with pytest.raises(GeminiClientError, match="network problem"):
        await generate_content_with_retry(client, model="m", contents="x")  # type: ignore[arg-type]
    assert client.models.calls == 4
