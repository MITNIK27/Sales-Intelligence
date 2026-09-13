"""In-house, free email verification: MX-record lookup + SMTP handshake probe (per the master
plan's Phase 5 spec — no paid verification service). Requires outbound TCP port 25, which many
networks/ISPs block by default; a blocked/unreachable network correctly maps to `"unknown"`, not
`"invalid"` — we don't claim to know an address is bad just because we couldn't reach the mail
server."""

import asyncio
import logging
import smtplib
import socket

import dns.exception
import dns.resolver

from app.modules.verification.providers.base import EmailVerificationProvider, VerificationResult

logger = logging.getLogger(__name__)

_SMTP_TIMEOUT_SECONDS = 8.0
_PROBE_FROM_ADDRESS = "verify-probe@example.com"

# SMTP reply codes that mean "the mailbox is confirmed to not exist" — a clear, permanent
# rejection. Everything else (4xx greylisting/throttling, unexpected 2xx variants) is treated as
# `unknown` rather than guessed at.
_SMTP_INVALID_CODES = {550, 551, 553, 554}
_SMTP_VALID_CODES = {250, 251}


def _resolve_mx_host(domain: str) -> tuple[str | None, VerificationResult | None]:
    """Returns (mx_host, None) on success, or (None, VerificationResult) when resolution itself
    already answers the question (e.g. domain doesn't exist)."""
    try:
        answers = dns.resolver.resolve(domain, "MX")
    except dns.resolver.NXDOMAIN:
        return None, VerificationResult(status="invalid", detail="domain does not exist")
    except dns.resolver.NoAnswer:
        return None, VerificationResult(status="unknown", detail="no MX records found for domain")
    except (dns.resolver.NoNameservers, dns.exception.Timeout) as exc:
        return None, VerificationResult(status="unknown", detail=f"DNS lookup failed: {exc}")

    if not answers:
        return None, VerificationResult(status="unknown", detail="no MX records found for domain")
    best = min(answers, key=lambda r: r.preference)
    return str(best.exchange).rstrip("."), None


def _probe_smtp(mx_host: str, email: str) -> VerificationResult:
    try:
        with smtplib.SMTP(mx_host, 25, timeout=_SMTP_TIMEOUT_SECONDS) as smtp:
            smtp.helo(socket.getfqdn())
            smtp.mail(_PROBE_FROM_ADDRESS)
            code, message = smtp.rcpt(email)
    except (OSError, smtplib.SMTPException) as exc:
        logger.info("smtp probe for %r via %s failed: %s", email, mx_host, exc)
        return VerificationResult(
            status="unknown",
            detail=f"could not reach mail server (port 25 may be blocked on this network): {exc}",
        )

    if code in _SMTP_VALID_CODES:
        return VerificationResult(status="valid", detail=f"SMTP {code}")
    if code in _SMTP_INVALID_CODES:
        return VerificationResult(status="invalid", detail=f"SMTP {code}: {message!r}")
    return VerificationResult(status="unknown", detail=f"SMTP {code}: {message!r}")


def _verify_email_sync(email: str) -> VerificationResult:
    if "@" not in email:
        return VerificationResult(status="invalid", detail="not a valid email format")
    domain = email.rsplit("@", 1)[-1].strip()

    mx_host, early_result = _resolve_mx_host(domain)
    if early_result is not None:
        return early_result
    assert mx_host is not None
    return _probe_smtp(mx_host, email)


class DnsSmtpEmailVerificationProvider(EmailVerificationProvider):
    async def verify_email(self, email: str) -> VerificationResult:
        return await asyncio.to_thread(_verify_email_sync, email)
