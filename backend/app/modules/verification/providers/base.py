"""Verification provider abstraction (Phase 5), matching the shape of `enrichment/providers/
base.py` — a frozen dataclass result type + single-method ABCs, one per channel type since email
and phone verification use entirely different mechanisms (MX/SMTP probe vs. format check)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

VerificationStatus = Literal["valid", "invalid", "unknown"]


@dataclass(frozen=True)
class VerificationResult:
    status: VerificationStatus
    detail: str | None = None


class EmailVerificationProvider(ABC):
    @abstractmethod
    async def verify_email(self, email: str) -> VerificationResult: ...


class PhoneVerificationProvider(ABC):
    @abstractmethod
    async def verify_phone(self, phone: str) -> VerificationResult: ...
