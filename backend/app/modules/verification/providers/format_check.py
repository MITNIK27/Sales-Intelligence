"""Phone verification per the master plan's Phase 5 spec: "format/pattern check for phone" —
structural validity only, not real deliverability (no carrier lookup, no paid API)."""

import re

from app.modules.verification.providers.base import PhoneVerificationProvider, VerificationResult

# Loose E.164-style check: optional leading '+', 7-15 digits total, not starting with 0.
# Deliberately permissive — this is a format sanity check, not a strict national-format validator.
_PHONE_RE = re.compile(r"^\+?[1-9]\d{6,14}$")


def _normalize_for_check(raw: str) -> str:
    return re.sub(r"[\s().-]", "", raw.strip())


class PatternPhoneVerificationProvider(PhoneVerificationProvider):
    async def verify_phone(self, phone: str) -> VerificationResult:
        cleaned = _normalize_for_check(phone)
        if _PHONE_RE.match(cleaned):
            return VerificationResult(status="valid", detail="matches expected phone format")
        return VerificationResult(status="invalid", detail="does not match expected phone format")
