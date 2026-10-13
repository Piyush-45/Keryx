"""Tenant model: organizations, users, memberships + RLS.

Revision ID: 0001
Revises:
Create Date: 2026-10-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from vp_db.rls import (
    CREATE_CURRENT_ORG_FN,
    CURRENT_ORG,
    DROP_CURRENT_ORG_FN,
    create_policy,
    enable_tenant_rls,
    force_rls,
)

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    # Default privileges (scripts/db/init.sql) grant the app role DML on every table vp_migrator
    # creates, including Alembic's bookkeeping table. The app must not touch it.
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'vp_app') THEN "
        "REVOKE ALL ON TABLE alembic_version FROM vp_app; END IF; END $$"
    )
    op.execute(CREATE_CURRENT_ORG_FN)

    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("region", sa.String(length=8), server_default=sa.text("'in'"), nullable=False),
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        *_timestamps(),
        sa.CheckConstraint("region IN ('in', 'us', 'eu')", name=op.f("ck_organizations_region")),
        sa.CheckConstraint(
            "length(name) BETWEEN 1 AND 200", name=op.f("ck_organizations_name_length")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)

    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'member')", name=op.f("ck_memberships_role")
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_memberships_org_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_memberships_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memberships")),
        sa.UniqueConstraint("org_id", "id", name=op.f("uq_memberships_org_id_id")),
        sa.UniqueConstraint("org_id", "user_id", name=op.f("uq_memberships_org_id_user_id")),
    )
    op.create_index(op.f("ix_memberships_org_id"), "memberships", ["org_id"])
    op.create_index(op.f("ix_memberships_user_id"), "memberships", ["user_id"])

    # organizations: tenant root, visible only to itself. Creating an org = scope to the new id,
    # then insert (the app generates the id).
    for stmt in force_rls("organizations"):
        op.execute(stmt)
    org_match = f"id = {CURRENT_ORG}"
    op.execute(
        create_policy("organizations", "tenant_isolation", using=org_match, with_check=org_match)
    )

    # memberships: standard tenant table.
    for stmt in enable_tenant_rls("memberships"):
        op.execute(stmt)

    # users: global identity. Readable only if a member of the current org; insertable from any
    # tenant context (invite flow inserts the user, then the membership). No UPDATE/DELETE policy
    # yet: a user spans orgs, so profile edits and deletion are decided with auth (Phase 3).
    for stmt in force_rls("users"):
        op.execute(stmt)
    is_member = (
        "EXISTS (SELECT 1 FROM memberships m "
        "WHERE m.user_id = users.id AND m.org_id = app_current_org())"
    )
    op.execute(create_policy("users", "member_read", command="SELECT", using=is_member))
    op.execute(
        create_policy(
            "users", "tenant_insert", command="INSERT", with_check=f"{CURRENT_ORG} IS NOT NULL"
        )
    )


def downgrade() -> None:
    op.execute("DROP POLICY member_read ON users")  # depends on memberships
    op.drop_table("memberships")
    op.drop_table("users")
    op.drop_table("organizations")
    op.execute(DROP_CURRENT_ORG_FN)
