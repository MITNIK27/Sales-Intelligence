"""The checks every API request goes through (Phase 9).

- `verified_identity`: the request carries a valid Firebase ID token for an allowed Google account.
  Used alone only by the few endpoints for people who have no access yet (`/auth/*`).
- `signed_in`: that person also has an active account here. Attached to every other router in
  `main.py`; `governance_checks/test_routes_require_sign_in.py` fails if a route misses it. It puts
  the person's id in the request's context, so model calls, jobs and audit lines record who acted.
- `require(action)`: their role may take this action (`permissions.py`).

Refusals carry `{"code", "message"}` so the browser can tell "sign in again" (401) from "no access
yet", "disabled" and "not allowed" (403)."""

from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.db.session import get_db
from app.modules.auth.models import USER_STATUS_ACTIVE, User
from app.modules.auth.permissions import Action, allowed
from app.modules.auth.service import resolve_user
from app.modules.auth.tokens import Identity, SignInError, verify_token
from app.modules.usage.context import usage_scope

_bearer = HTTPBearer(auto_error=False)


def _refuse(status: int, code: str, message: str) -> HTTPException:
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return HTTPException(status, detail={"code": code, "message": message}, headers=headers)


async def verified_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Identity:
    if credentials is None or not credentials.credentials:
        raise _refuse(401, "signed_out", "Sign in to continue.")
    try:
        return await verify_token(credentials.credentials, get_settings())
    except SignInError as exc:
        code = {401: "signed_out", 403: "not_allowed", 503: "unavailable"}.get(exc.status, "error")
        raise _refuse(exc.status, code, str(exc)) from exc


async def signed_in(
    identity: Identity = Depends(verified_identity),
    session: AsyncSession = Depends(get_db),
) -> AsyncIterator[User]:
    user, changed = await resolve_user(session, identity, get_settings())
    if changed:
        await session.commit()  # a linked invitation or the sign-in time; nothing else is pending
    if user is None:
        raise _refuse(403, "no_access", "You do not have access yet. Ask an admin for access.")
    if user.status != USER_STATUS_ACTIVE:
        raise _refuse(403, "disabled", "Your access has been switched off. Ask an admin.")
    if user.organization_id != DEFAULT_ORGANIZATION_ID:
        raise _refuse(403, "no_access", "Your account belongs to another organisation.")
    with usage_scope(user_id=user.id):
        yield user


class _Require:
    """A dependency that checks one action; kept as a class so checks can find which action a
    route requires."""

    def __init__(self, action: Action) -> None:
        self.action = action

    async def __call__(self, user: User = Depends(signed_in)) -> User:
        if not allowed(user.role, self.action):
            raise _refuse(
                403,
                "forbidden",
                f"Your role ({user.role}) cannot do this. Ask an admin or manager.",
            )
        return user


def require(action: Action) -> Callable[..., Awaitable[User]]:
    return _Require(action)
