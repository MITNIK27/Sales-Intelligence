"""Sign-in and the Users page (Phase 9).

`/auth/*` serves a person whose Google account is verified but who may not have access yet: who am
I, and "ask an admin for access". `/users/*` is the Users page, for admins and managers."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.db.session import get_db
from app.modules.auth import service
from app.modules.auth.deps import require, verified_identity
from app.modules.auth.models import USER_STATUS_ACTIVE, User
from app.modules.auth.permissions import Action, actions_for
from app.modules.auth.schemas import (
    AccessRequestIn,
    AccessRequestOut,
    AccessRequestResult,
    ApproveIn,
    InviteIn,
    MeOut,
    PendingCount,
    UserOut,
    UserUpdate,
)
from app.modules.auth.tokens import Identity

auth_router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(
    prefix="/users", tags=["users"], dependencies=[Depends(require(Action.USERS_MANAGE))]
)


def _user_out(user: User, names: dict[uuid.UUID, str] | None = None) -> UserOut:
    out = UserOut.model_validate(user)
    out.has_signed_in = user.firebase_uid is not None
    if user.invited_by is not None and names:
        out.invited_by_name = names.get(user.invited_by)
    return out


async def _with_names(session: AsyncSession, users: list[User]) -> list[UserOut]:
    names = await service.emails_by_id(
        session, {u.invited_by for u in users if u.invited_by is not None}
    )
    return [_user_out(u, names) for u in users]


def _refusal(exc: service.AccessError) -> HTTPException:
    return HTTPException(exc.status, detail={"code": "refused", "message": str(exc)})


@auth_router.get("/me", response_model=MeOut)
async def me(
    identity: Identity = Depends(verified_identity), session: AsyncSession = Depends(get_db)
) -> MeOut:
    user, changed = await service.resolve_user(session, identity, get_settings())
    if changed:
        await session.commit()
    if user is None:
        pending = await service.pending_request(session, identity.email)
        return MeOut(
            access="none",
            email=identity.email,
            name=identity.name,
            request_pending=pending is not None,
        )
    if user.status != USER_STATUS_ACTIVE:
        return MeOut(access="disabled", email=identity.email, name=identity.name)
    return MeOut(
        access="granted",
        email=user.email,
        name=user.display_name or identity.name,
        user=(await _with_names(session, [user]))[0],
        actions=actions_for(user.role),
    )


@auth_router.post("/access-requests", response_model=AccessRequestResult, status_code=201)
async def ask_for_access(
    body: AccessRequestIn,
    identity: Identity = Depends(verified_identity),
    session: AsyncSession = Depends(get_db),
) -> AccessRequestResult:
    """ "Ask an admin for access", from someone signed in with an allowed account but no invitation.
    Admins and managers see it on the Users page."""
    user, _ = await service.resolve_user(session, identity, get_settings())
    if user is not None:
        message = (
            "You already have access."
            if user.status == USER_STATUS_ACTIVE
            else "Your access has been switched off. Ask an admin directly."
        )
        raise HTTPException(409, detail={"code": "refused", "message": message})
    request, already = await service.request_access(session, identity, body.message)
    await session.commit()
    return AccessRequestResult(
        request=AccessRequestOut.model_validate(request), already_waiting=already
    )


@users_router.get("", response_model=list[UserOut])
async def list_users(session: AsyncSession = Depends(get_db)) -> list[UserOut]:
    return await _with_names(session, await service.list_users(session, DEFAULT_ORGANIZATION_ID))


@users_router.post("", response_model=UserOut, status_code=201)
async def invite(
    body: InviteIn,
    actor: User = Depends(require(Action.USERS_MANAGE)),
    session: AsyncSession = Depends(get_db),
) -> UserOut:
    try:
        user = await service.invite_user(session, actor, body.email, body.role, get_settings())
    except service.AccessError as exc:
        raise _refusal(exc) from exc
    await session.commit()
    return _user_out(user)


@users_router.patch("/{user_id}", response_model=UserOut)
async def update(
    user_id: uuid.UUID,
    body: UserUpdate,
    actor: User = Depends(require(Action.USERS_MANAGE)),
    session: AsyncSession = Depends(get_db),
) -> UserOut:
    try:
        user = await service.update_user(
            session, actor, user_id, role=body.role, status=body.status
        )
    except service.AccessError as exc:
        raise _refusal(exc) from exc
    await session.commit()
    return _user_out(user)


@users_router.delete("/{user_id}", status_code=204)
async def remove_invitation(
    user_id: uuid.UUID,
    actor: User = Depends(require(Action.USERS_MANAGE)),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Takes back an invitation nobody has used yet."""
    try:
        await service.remove_invitation(session, actor, user_id)
    except service.AccessError as exc:
        raise _refusal(exc) from exc
    await session.commit()


@users_router.get("/access-requests", response_model=list[AccessRequestOut])
async def access_requests(
    status: str | None = "pending", session: AsyncSession = Depends(get_db)
) -> list[AccessRequestOut]:
    rows = await service.list_requests(session, DEFAULT_ORGANIZATION_ID, status or None)
    return [AccessRequestOut.model_validate(r) for r in rows]


@users_router.get("/access-requests/count", response_model=PendingCount)
async def access_requests_count(session: AsyncSession = Depends(get_db)) -> PendingCount:
    return PendingCount(pending=await service.count_pending(session, DEFAULT_ORGANIZATION_ID))


@users_router.post("/access-requests/{request_id}/approve", response_model=AccessRequestOut)
async def approve(
    request_id: uuid.UUID,
    body: ApproveIn,
    actor: User = Depends(require(Action.USERS_MANAGE)),
    session: AsyncSession = Depends(get_db),
) -> AccessRequestOut:
    try:
        request = await service.approve_request(
            session, actor, request_id, body.role, get_settings()
        )
    except service.AccessError as exc:
        raise _refusal(exc) from exc
    await session.commit()
    return AccessRequestOut.model_validate(request)


@users_router.post("/access-requests/{request_id}/dismiss", response_model=AccessRequestOut)
async def dismiss(
    request_id: uuid.UUID,
    actor: User = Depends(require(Action.USERS_MANAGE)),
    session: AsyncSession = Depends(get_db),
) -> AccessRequestOut:
    try:
        request = await service.dismiss_request(session, actor, request_id)
    except service.AccessError as exc:
        raise _refusal(exc) from exc
    await session.commit()
    return AccessRequestOut.model_validate(request)
