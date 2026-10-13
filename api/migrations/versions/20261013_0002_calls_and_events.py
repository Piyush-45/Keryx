"""Calls and call events, with tenant RLS.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from vp_db.rls import enable_tenant_rls

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'queued'"), nullable=False
        ),
        sa.Column("agent_version_id", sa.Uuid(), nullable=True),
        sa.Column("campaign_id", sa.Uuid(), nullable=True),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("from_number", sa.Text(), nullable=True),
        sa.Column("to_number", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_by", sa.String(length=16), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "cost",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "direction IN ('inbound', 'outbound', 'web')", name=op.f("ck_calls_direction")
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'ringing', 'in_progress', 'completed', 'failed', 'no_answer',"
            " 'busy', 'canceled')",
            name=op.f("ck_calls_status"),
        ),
        sa.CheckConstraint(
            "ended_by IS NULL OR ended_by IN ('caller', 'agent', 'timeout', 'error', 'transfer',"
            " 'system')",
            name=op.f("ck_calls_ended_by"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_calls_org_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calls")),
        sa.UniqueConstraint("org_id", "id", name=op.f("uq_calls_org_id_id")),
    )
    op.create_index(op.f("ix_calls_org_id"), "calls", ["org_id"])

    op.create_table(
        "call_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("call_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("v", sa.SmallInteger(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "call_id"],
            ["calls.org_id", "calls.id"],
            name=op.f("fk_call_events_org_id_call_id_calls"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_call_events_org_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_call_events")),
        sa.UniqueConstraint("org_id", "id", name=op.f("uq_call_events_org_id_id")),
        sa.UniqueConstraint(
            "org_id", "call_id", "seq", name=op.f("uq_call_events_org_id_call_id_seq")
        ),
    )

    for table in ("calls", "call_events"):
        for stmt in enable_tenant_rls(table):
            op.execute(stmt)


def downgrade() -> None:
    op.drop_table("call_events")
    op.drop_table("calls")
