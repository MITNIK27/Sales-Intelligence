import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UpdatedAtMixin, new_uuid

USER_ROLE_ADMIN = "admin"
USER_ROLE_MANAGER = "manager"
USER_ROLE_REP = "rep"
USER_ROLES = (USER_ROLE_ADMIN, USER_ROLE_MANAGER, USER_ROLE_REP)

USER_STATUS_ACTIVE = "active"
USER_STATUS_DISABLED = "disabled"
USER_STATUSES = (USER_STATUS_ACTIVE, USER_STATUS_DISABLED)


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), unique=True)

    users: Mapped[list["User"]] = relationship(back_populates="organization")


class User(Base, TimestampMixin, UpdatedAtMixin):
    """A person who signs in. Sign-in itself is Firebase Authentication (Phase 8 decision): Firebase
    holds the credentials, this table holds everything else about the person, linked by
    `firebase_uid`. No password is ever stored here. A person who leaves is disabled, not deleted,
    so the decisions they made keep pointing at them."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'manager', 'rep')", name="role"),
        CheckConstraint("status IN ('active', 'disabled')", name="status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    # Firebase's user id (at most 128 characters), the only link to the sign-in account.
    firebase_uid: Mapped[str] = mapped_column(String(128), unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(
        String(20), default=USER_ROLE_REP, server_default=USER_ROLE_REP
    )
    status: Mapped[str] = mapped_column(
        String(20), default=USER_STATUS_ACTIVE, server_default=USER_STATUS_ACTIVE
    )
    last_sign_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    organization: Mapped[Organization] = relationship(back_populates="users")
