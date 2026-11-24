"""Checking a Firebase ID token: is this really a signed-in InfoBeans Google account?

The browser signs in with Google through Firebase and sends the resulting ID token on every request.
Here the token's signature is checked against Google's published certificates for Firebase, and its
audience, issuer and expiry against our project. That needs only the project ID: no service-account
key, so there is no secret to keep. On top of the signature, three rules of our own:
- the email is verified;
- it came from Google sign-in (not another provider someone enabled later);
- the email's domain is one we allow (`AUTH_ALLOWED_DOMAINS`).

Passing here only proves who the person is. Whether they may use the app (an invitation, an active
account, their role) is decided by our own database in `service.py`."""

import re
import time
from dataclasses import dataclass
from typing import Any

import httpx
from google.auth import exceptions as google_exceptions
from google.auth import jwt as google_jwt

from app.core.config import Settings

_CERTS_URL = (
    "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
)
_DEFAULT_CACHE_SECONDS = 3600
_CLOCK_SKEW_SECONDS = 30
_MAX_AGE = re.compile(r"max-age=(\d+)")


class SignInError(Exception):
    """The request cannot be accepted as a signed-in person. `status` is the HTTP answer: 401 when
    signing in again may help, 403 when it will not (an account from another domain), 503 when we
    could not check at all."""

    def __init__(self, message: str, status: int = 401) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Identity:
    """Who the token says the person is. Email is lower-case."""

    uid: str
    email: str
    name: str | None


_certs: dict[str, str] = {}
_certs_until = 0.0


async def _download_certs() -> tuple[dict[str, str], float]:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(_CERTS_URL)
    response.raise_for_status()
    match = _MAX_AGE.search(response.headers.get("cache-control", ""))
    seconds = int(match.group(1)) if match else _DEFAULT_CACHE_SECONDS
    return dict(response.json()), seconds


async def google_certificates() -> dict[str, str]:
    """Google's current signing certificates for Firebase tokens, kept for as long as Google says
    they may be (usually hours), so a request normally makes no outside call."""
    global _certs, _certs_until
    if _certs and time.monotonic() < _certs_until:
        return _certs
    try:
        certs, seconds = await _download_certs()
    except (httpx.HTTPError, ValueError) as exc:
        if _certs:  # an outage at Google: the keys we have are still the best answer
            return _certs
        raise SignInError(
            "Could not check your sign-in right now. Try again shortly.", 503
        ) from exc
    _certs, _certs_until = certs, time.monotonic() + seconds
    return _certs


def _domain_allowed(email: str, domains: list[str]) -> bool:
    return any(email.endswith("@" + domain) for domain in domains)


def check_claims(claims: dict[str, Any], settings: Settings) -> Identity:
    """Our own rules on a token whose signature, audience and expiry already passed."""
    project = settings.firebase_project_id
    if claims.get("iss") != f"https://securetoken.google.com/{project}":
        raise SignInError("This sign-in is not for this app. Sign in again.")
    uid = str(claims.get("sub") or "")
    if not uid:
        raise SignInError("This sign-in has no account. Sign in again.")
    provider = (claims.get("firebase") or {}).get("sign_in_provider")
    if provider != "google.com":
        raise SignInError("Sign in with your InfoBeans Google account.", 403)
    email = str(claims.get("email") or "").strip().lower()
    if not email or not claims.get("email_verified"):
        raise SignInError("Your Google account's email is not verified.", 403)
    if not _domain_allowed(email, settings.allowed_domains):
        allowed = ", ".join("@" + d for d in settings.allowed_domains) or "no domain"
        raise SignInError(f"Only {allowed} accounts can use this app.", 403)
    name = claims.get("name")
    return Identity(uid=uid, email=email, name=str(name)[:255] if name else None)


async def verify_token(token: str, settings: Settings) -> Identity:
    """The person behind a Firebase ID token, or `SignInError`."""
    if not settings.firebase_project_id:
        raise SignInError("Sign-in is not configured on the server (FIREBASE_PROJECT_ID).", 503)
    certs = await google_certificates()
    try:
        claims: dict[str, Any] = google_jwt.decode(  # type: ignore[no-untyped-call]
            token,
            certs=certs,
            audience=settings.firebase_project_id,
            clock_skew_in_seconds=_CLOCK_SKEW_SECONDS,
        )
    except (ValueError, google_exceptions.GoogleAuthError) as exc:
        raise SignInError("Your sign-in has expired or is not valid. Sign in again.") from exc
    return check_claims(claims, settings)
