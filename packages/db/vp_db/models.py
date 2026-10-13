"""Tenant model (first cut). Every tenant-owned table:
- has `org_id` -> organizations.id ON DELETE RESTRICT and UNIQUE (org_id, id)
- references other tenant tables with composite FKs that include org_id
- gets RLS via `vp_db.rls.enable_tenant_rls` in its migration
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from vp_db.base import Base, TimestampMixin

REGIONS = ("in", "us", "eu")
MEMBER_ROLES = ("owner", "admin", "member")
CALL_DIRECTIONS = ("inbound", "outbound", "web")
CALL_STATUSES = (
    "queued",
    "ringing",
    "in_progress",
    "completed",
    "failed",
    "no_answer",
    "busy",
    "canceled",
)
CALL_ENDED_BY = ("caller", "agent", "timeout", "error", "transfer", "system")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Organization(TimestampMixin, Base):
    """Tenant root. Visible only while scoped to itself (`id = app_current_org()`)."""

    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(_in("region", REGIONS), name="region"),
        CheckConstraint("length(name) BETWEEN 1 AND 200", name="name_length"),
    )
    # Ids are generated app-side: creating an org means scoping to the new id, then inserting.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text)
    region: Mapped[str] = mapped_column(String(8), server_default=text("'in'"))
    settings: Mapped[dict[str, object]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class User(TimestampMixin, Base):
    """Global identity (no org_id). Visible only if a member of the current org.

    Insert without RETURNING (no eager server defaults): the new row is not visible until its
    membership exists, and Postgres applies the SELECT policy to RETURNING rows.
    """

    __tablename__ = "users"
    __table_args__ = (Index("uq_users_email_lower", func.lower(text("email")), unique=True),)
    __mapper_args__ = {"eager_defaults": False}  # noqa: RUF012  (SQLAlchemy-typed attribute)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text)


class Membership(TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("org_id", "id"),
        UniqueConstraint("org_id", "user_id"),
        CheckConstraint(_in("role", MEMBER_ROLES), name="role"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))


class Call(TimestampMixin, Base):
    """One phone/web call. Created by the API (inbound webhook, campaign dialer) before the worker
    starts; the event consumer fills in started/ended fields from call.started / call.ended."""

    __tablename__ = "calls"
    __table_args__ = (
        UniqueConstraint("org_id", "id"),
        CheckConstraint(_in("direction", CALL_DIRECTIONS), name="direction"),
        CheckConstraint(_in("status", CALL_STATUSES), name="status"),
        CheckConstraint(f"ended_by IS NULL OR {_in('ended_by', CALL_ENDED_BY)}", name="ended_by"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    direction: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'queued'"))
    # FKs to agent_versions / campaigns / contacts are added (composite, with org_id) in the
    # migrations that create those tables.
    agent_version_id: Mapped[uuid.UUID | None]
    campaign_id: Mapped[uuid.UUID | None]
    contact_id: Mapped[uuid.UUID | None]
    from_number: Mapped[str | None] = mapped_column(Text)
    to_number: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_by: Mapped[str | None] = mapped_column(String(16))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    cost: Mapped[dict[str, object]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class CallEventRow(Base):
    """A persisted call event (decision 0007). `payload` is validated by vp_shared.events before
    insert; `id` is the event id, so redelivered events are ignored."""

    __tablename__ = "call_events"
    __table_args__ = (
        UniqueConstraint("org_id", "id"),
        UniqueConstraint("org_id", "call_id", "seq"),
        ForeignKeyConstraint(
            ["org_id", "call_id"], ["calls.org_id", "calls.id"], ondelete="CASCADE"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"))
    call_id: Mapped[uuid.UUID]
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(32))
    v: Mapped[int] = mapped_column(SmallInteger)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
