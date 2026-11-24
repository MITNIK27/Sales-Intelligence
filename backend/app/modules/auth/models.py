import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UpdatedAtMixin, new_uuid

USER_ROLE_ADMIN = "admin"
USER_ROLE_MANAGER = "manager"
USER_ROLE_REP = "rep"
USER_ROLES = (USER_ROLE_ADMIN, USER_ROLE_MANAGER, USER_ROLE_REP)

USER_STATUS_ACTIVE = "active"
USER_STATUS_DISABLED = "disabled"
USER_STATUSES = (USER_STATUS_ACTIVE, USER_STATUS_DISABLED)

REQUEST_PENDING = "pending"
REQUEST_APPROVED = "approved"
REQUEST_DISMISSED = "dismissed"
REQUEST_STATUSES = (REQUEST_PENDING, REQUEST_APPROVED, REQUEST_DISMISSED)


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), unique=True)

    users: Mapped[list["User"]] = relationship(back_populates="organization")


class User(Base, TimestampMixin, UpdatedAtMixin):
    """A person who signs in. Sign-in itself is Firebase Authentication (Phase 8 decision): Firebase
    holds the credentials, this table holds everything else about the person, linked by
    `firebase_uid`. No password is ever stored here. A person who leaves is disabled, not deleted,
    so the decisions they made keep pointing at them.

    Access is by invitation (Phase 9): an admin or manager adds the email and role first, which
    makes a row with no `firebase_uid`; the first sign-in with that Google account links it. Emails
    are stored lower-case."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'manager', 'rep')", name="role"),
        CheckConstraint("status IN ('active', 'disabled')", name="status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    # Firebase's user id (at most 128 characters), the only link to the sign-in account. Empty for
    # an invitation nobody has used yet.
    firebase_uid: Mapped[str | None] = mapped_column(String(128), unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(
        String(20), default=USER_ROLE_REP, server_default=USER_ROLE_REP
    )
    status: Mapped[str] = mapped_column(
        String(20), default=USER_STATUS_ACTIVE, server_default=USER_STATUS_ACTIVE
    )
    last_sign_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Who invited them (empty for the first admin, who comes from AUTH_BOOTSTRAP_ADMINS).
    invited_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)

    organization: Mapped[Organization] = relationship(back_populates="users")


class AccessRequest(Base):
    """Someone signed in with an allowed Google account but has no invitation, and asked for access.
    Admins and managers see it in the app and approve it (which invites them with a role) or dismiss
    it. Kept after the decision as a record."""

    __tablename__ = "access_requests"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'dismissed')", name="status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    firebase_uid: Mapped[str | None] = mapped_column(String(128))
    message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), default=REQUEST_PENDING, server_default=REQUEST_PENDING, index=True
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # When admins were told by email, and why that failed (email is not switched on yet).
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notify_error: Mapped[str | None] = mapped_column(String(300))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
