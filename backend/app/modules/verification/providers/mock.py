"""Canned in-memory provider implementations for tests only — no network/DNS calls."""

from app.modules.verification.providers.base import (
    EmailVerificationProvider,
    PhoneVerificationProvider,
    VerificationResult,
)


class MockEmailVerificationProvider(EmailVerificationProvider):
    def __init__(self, result: VerificationResult | None = None) -> None:
        self._result = result or VerificationResult(status="valid")

    async def verify_email(self, email: str) -> VerificationResult:
        return self._result


class MockPhoneVerificationProvider(PhoneVerificationProvider):
    def __init__(self, result: VerificationResult | None = None) -> None:
        self._result = result or VerificationResult(status="valid")

    async def verify_phone(self, phone: str) -> VerificationResult:
        return self._result
