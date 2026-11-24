"""Who may use the app, decided by our own database (Phase 9).

A verified Google account (`tokens.py`) is matched to a `users` row: by its Firebase id, else by
email, which is how an invitation is taken up on the first sign-in. No row means no access yet; the
person can ask for it. The first admin comes from `AUTH_BOOTSTRAP_ADMINS`.

Rules on the Users page, enforced here (not only in the screen):
- only an admin may make someone an admin, or change or disable an admin;
- nobody may change their own role or disable themselves (another admin or manager can);
- an invitation nobody has used yet can be removed; an account that has signed in is deactivated,
  never deleted, so its history keeps pointing at it;
- the last active admin cannot be demoted or disabled."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.modules.auth.models import (
    REQUEST_APPROVED,
    REQUEST_DISMISSED,
    REQUEST_PENDING,
    USER_ROLE_ADMIN,
    USER_ROLES,
    USER_STATUS_ACTIVE,
    USER_STATUS_DISABLED,
    USER_STATUSES,
    AccessRequest,
    User,
)
from app.modules.auth.permissions import Action, allowed
from app.modules.auth.tokens import Identity

logger = logging.getLogger(__name__)

# How often "last signed in" is written: every request would be a write for nothing.
_SIGN_IN_STAMP = timedelta(minutes=15)
# One access request per person in this window; asking again shows the waiting one.
REQUEST_WINDOW = timedelta(hours=24)


class AccessError(Exception):
    """A Users-page action that is not allowed or not possible. `status` is the HTTP answer."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def normalise_email(email: str) -> str:
    return email.strip().lower()


def _now() -> datetime:
    return datetime.now(UTC)


# -- signing in -----------------------------------------------------------------------------------


async def _user_by(session: AsyncSession, **match: str) -> User | None:
    column, value = next(iter(match.items()))
    return (
        await session.execute(select(User).where(getattr(User, column) == value))
    ).scalar_one_or_none()


async def resolve_user(
    session: AsyncSession, identity: Identity, settings: Settings
) -> tuple[User | None, bool]:
    """The person's account and whether it was changed (so the caller saves it). Links an
    invitation on first sign-in, creates the bootstrap admin, refreshes name and last sign-in."""
    changed = False
    user = await _user_by(session, firebase_uid=identity.uid)
    if user is None:
        user = await _user_by(session, email=identity.email)
        if user is not None:
            if user.firebase_uid and user.firebase_uid != identity.uid:
                # The same email on a different Google account: refuse rather than guess.
                logger.warning("sign-in for %s from an unexpected account", identity.email)
                return None, False
            user.firebase_uid = identity.uid
            changed = True
        elif identity.email in settings.bootstrap_admins:
            user = User(
                organization_id=DEFAULT_ORGANIZATION_ID,
                firebase_uid=identity.uid,
                email=identity.email,
                display_name=identity.name,
                role=USER_ROLE_ADMIN,
                status=USER_STATUS_ACTIVE,
            )
            session.add(user)
            logger.info("first admin %s signed in (AUTH_BOOTSTRAP_ADMINS)", identity.email)
            changed = True
        else:
            return None, False
    if identity.name and not user.display_name:
        user.display_name = identity.name
        changed = True
    now = _now()
    if user.last_sign_in_at is None or now - user.last_sign_in_at > _SIGN_IN_STAMP:
        user.last_sign_in_at = now
        changed = True
    if changed:
        await session.flush()
    return user, changed


# -- the Users page -------------------------------------------------------------------------------


async def list_users(session: AsyncSession, organization_id: uuid.UUID) -> list[User]:
    return list(
        (
            await session.execute(
                select(User)
                .where(User.organization_id == organization_id)
                .order_by(User.status, User.email)
            )
        )
        .scalars()
        .all()
    )


def _check_role(role: str) -> None:
    if role not in USER_ROLES:
        raise AccessError(f"Unknown role {role!r}.")


def _may_grant(actor: User, role: str) -> None:
    if role == USER_ROLE_ADMIN and not allowed(actor.role, Action.USERS_GRANT_ADMIN):
        raise AccessError("Only an admin can make someone an admin.", 403)


async def invite_user(
    session: AsyncSession, actor: User, email: str, role: str, settings: Settings
) -> User:
    """An invitation: the person can sign in with this Google account from now on."""
    email = normalise_email(email)
    _check_role(role)
    _may_grant(actor, role)
    if "@" not in email or not any(email.endswith("@" + d) for d in settings.allowed_domains):
        allowed_domains = ", ".join("@" + d for d in settings.allowed_domains)
        raise AccessError(f"Only {allowed_domains} addresses can be invited.")
    existing = await _user_by(session, email=email)
    if existing is not None:
        state = "is disabled" if existing.status == USER_STATUS_DISABLED else "already has access"
        raise AccessError(f"{email} {state}.", 409)
    user = User(
        organization_id=actor.organization_id,
        email=email,
        role=role,
        status=USER_STATUS_ACTIVE,
        invited_by=actor.id,
    )
    session.add(user)
    await session.flush()
    return user


async def _active_admins(session: AsyncSession, organization_id: uuid.UUID) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.organization_id == organization_id,
                User.role == USER_ROLE_ADMIN,
                User.status == USER_STATUS_ACTIVE,
            )
        )
    ) or 0


async def update_user(
    session: AsyncSession,
    actor: User,
    user_id: uuid.UUID,
    *,
    role: str | None = None,
    status: str | None = None,
) -> User:
    user = await session.get(User, user_id)
    if user is None or user.organization_id != actor.organization_id:
        raise AccessError("No such person.", 404)
    if role is not None:
        _check_role(role)
    if status is not None and status not in USER_STATUSES:
        raise AccessError(f"Unknown status {status!r}.")
    if user.role == USER_ROLE_ADMIN and not allowed(actor.role, Action.USERS_GRANT_ADMIN):
        raise AccessError("Only an admin can change an admin.", 403)
    if role is not None:
        _may_grant(actor, role)
    if user.id == actor.id and role is not None and role != user.role:
        raise AccessError("You cannot change your own role. Ask another admin.")
    if status == USER_STATUS_DISABLED and user.id == actor.id:
        raise AccessError("You cannot deactivate yourself.")
    stays_admin = (role or user.role) == USER_ROLE_ADMIN and (status or user.status) == (
        USER_STATUS_ACTIVE
    )
    if (
        user.role == USER_ROLE_ADMIN
        and user.status == USER_STATUS_ACTIVE
        and not stays_admin
        and await _active_admins(session, user.organization_id) <= 1
    ):
        raise AccessError("This is the last active admin. Make someone else an admin first.")
    if role is not None:
        user.role = role
    if status is not None:
        user.status = status
    await session.flush()
    return user


async def remove_invitation(session: AsyncSession, actor: User, user_id: uuid.UUID) -> None:
    """Takes back an invitation nobody has used. Someone who has signed in is deactivated instead,
    so what they did stays attributed to them."""
    user = await session.get(User, user_id)
    if user is None or user.organization_id != actor.organization_id:
        raise AccessError("No such person.", 404)
    if user.firebase_uid is not None:
        raise AccessError("This person has already signed in. Deactivate them instead.", 409)
    if user.role == USER_ROLE_ADMIN and not allowed(actor.role, Action.USERS_GRANT_ADMIN):
        raise AccessError("Only an admin can remove an admin's invitation.", 403)
    await session.delete(user)
    await session.flush()


async def emails_by_id(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Names (or emails) of these people, for "invited by"."""
    if not ids:
        return {}
    rows = await session.execute(
        select(User.id, User.display_name, User.email).where(User.id.in_(ids))
    )
    return {uid: name or email for uid, name, email in rows.all()}


# -- access requests ------------------------------------------------------------------------------


async def notify_admins(request: AccessRequest) -> None:
    """Where admins will be emailed about a new request, once a mailbox is approved. For now the
    request is shown in the app (the Users page and its badge) and only logged here."""
    logger.info("access requested by %s (shown on the Users page)", request.email)


async def request_access(
    session: AsyncSession, identity: Identity, message: str | None
) -> tuple[AccessRequest, bool]:
    """The person's request, and whether it was already there (asked within the last 24 hours)."""
    latest = (
        await session.execute(
            select(AccessRequest)
            .where(AccessRequest.email == identity.email)
            .order_by(AccessRequest.requested_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    now = _now()
    if latest is not None and now - latest.requested_at < REQUEST_WINDOW:
        return latest, True
    note = " ".join((message or "").split())[:1000] or None
    if latest is not None and latest.status == REQUEST_PENDING:
        latest.requested_at, latest.message = now, note or latest.message
        request = latest
    else:
        request = AccessRequest(
            organization_id=DEFAULT_ORGANIZATION_ID,
            email=identity.email,
            display_name=identity.name,
            firebase_uid=identity.uid,
            message=note,
            status=REQUEST_PENDING,
            requested_at=now,
        )
        session.add(request)
    await session.flush()
    await notify_admins(request)
    return request, False


async def pending_request(session: AsyncSession, email: str) -> AccessRequest | None:
    return (
        await session.execute(
            select(AccessRequest).where(
                AccessRequest.email == email, AccessRequest.status == REQUEST_PENDING
            )
        )
    ).scalar_one_or_none()


async def list_requests(
    session: AsyncSession, organization_id: uuid.UUID, status: str | None = REQUEST_PENDING
) -> list[AccessRequest]:
    stmt = select(AccessRequest).where(AccessRequest.organization_id == organization_id)
    if status is not None:
        stmt = stmt.where(AccessRequest.status == status)
    return list(
        (await session.execute(stmt.order_by(AccessRequest.requested_at.desc()))).scalars().all()
    )


async def count_pending(session: AsyncSession, organization_id: uuid.UUID) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(AccessRequest)
            .where(
                AccessRequest.organization_id == organization_id,
                AccessRequest.status == REQUEST_PENDING,
            )
        )
    ) or 0


async def _request(session: AsyncSession, actor: User, request_id: uuid.UUID) -> AccessRequest:
    request = await session.get(AccessRequest, request_id)
    if request is None or request.organization_id != actor.organization_id:
        raise AccessError("No such request.", 404)
    if request.status != REQUEST_PENDING:
        raise AccessError("This request has already been handled.", 409)
    return request


async def approve_request(
    session: AsyncSession, actor: User, request_id: uuid.UUID, role: str, settings: Settings
) -> AccessRequest:
    """Invites the person with this role; they can sign in straight away."""
    request = await _request(session, actor, request_id)
    if await _user_by(session, email=request.email) is None:
        await invite_user(session, actor, request.email, role, settings)
    request.status, request.decided_by, request.decided_at = REQUEST_APPROVED, actor.id, _now()
    await session.flush()
    return request


async def dismiss_request(
    session: AsyncSession, actor: User, request_id: uuid.UUID
) -> AccessRequest:
    request = await _request(session, actor, request_id)
    request.status, request.decided_by, request.decided_at = REQUEST_DISMISSED, actor.id, _now()
    await session.flush()
    return request
