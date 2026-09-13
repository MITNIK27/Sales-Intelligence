import dns.exception
import dns.resolver
import pytest

from app.modules.verification.providers.dns_smtp import (
    DnsSmtpEmailVerificationProvider,
    _resolve_mx_host,
)
from app.modules.verification.providers.format_check import PatternPhoneVerificationProvider


@pytest.mark.parametrize(
    ("phone", "expected_status"),
    [
        ("+14155552671", "valid"),
        ("14155552671", "valid"),
        ("+91 98765 43210", "valid"),
        ("(415) 555-2671", "valid"),
        ("not-a-phone", "invalid"),
        ("123", "invalid"),
        ("0123456789", "invalid"),  # leading zero not allowed by the format check
    ],
)
async def test_pattern_phone_verification(phone: str, expected_status: str) -> None:
    provider = PatternPhoneVerificationProvider()
    result = await provider.verify_phone(phone)
    assert result.status == expected_status


async def test_verify_email_rejects_malformed_address() -> None:
    provider = DnsSmtpEmailVerificationProvider()
    result = await provider.verify_email("not-an-email")
    assert result.status == "invalid"


def test_resolve_mx_host_returns_invalid_for_nonexistent_domain(monkeypatch) -> None:
    def fake_resolve(domain, record_type):
        raise dns.resolver.NXDOMAIN()

    monkeypatch.setattr(dns.resolver, "resolve", fake_resolve)
    host, result = _resolve_mx_host("this-domain-does-not-exist-xyz123.invalid")
    assert host is None
    assert result is not None
    assert result.status == "invalid"


def test_resolve_mx_host_returns_unknown_when_dns_lookup_fails(monkeypatch) -> None:
    def fake_resolve(domain, record_type):
        raise dns.exception.Timeout()

    monkeypatch.setattr(dns.resolver, "resolve", fake_resolve)
    host, result = _resolve_mx_host("example.com")
    assert host is None
    assert result is not None
    assert result.status == "unknown"


async def test_verify_email_maps_smtp_connection_failure_to_unknown(monkeypatch) -> None:
    """On a network where port 25 is blocked (common), the probe must never claim `invalid` —
    only `unknown`, since we genuinely couldn't determine anything."""
    from app.modules.verification.providers import dns_smtp

    def fake_resolve_mx_host(domain):
        return "mail.example.com", None

    def fake_probe_smtp(mx_host, email):
        return dns_smtp.VerificationResult(status="unknown", detail="could not reach mail server")

    monkeypatch.setattr(dns_smtp, "_resolve_mx_host", fake_resolve_mx_host)
    monkeypatch.setattr(dns_smtp, "_probe_smtp", fake_probe_smtp)

    provider = DnsSmtpEmailVerificationProvider()
    result = await provider.verify_email("someone@example.com")
    assert result.status == "unknown"
