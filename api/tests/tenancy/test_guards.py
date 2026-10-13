"""Structural guards: catch a new table or role setup that would silently weaken isolation."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from vp_db.base import Base

SM = async_sessionmaker[AsyncSession]
BOOKKEEPING = {"alembic_version"}


def test_every_table_has_forced_rls_and_a_policy(migrated: None, owner_engine: Engine) -> None:
    with owner_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,"
                " (SELECT count(*) FROM pg_policies p"
                "   WHERE p.schemaname = 'public' AND p.tablename = c.relname)"
                " FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
                " WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')"
            )
        ).all()
    tables = {r[0] for r in rows}
    assert {"organizations", "users", "memberships"} <= tables
    missing = [r[0] for r in rows if r[0] not in BOOKKEEPING and not (r[1] and r[2] and r[3] > 0)]
    assert missing == [], f"tables without ENABLE+FORCE RLS and a policy: {missing}"


def test_tenant_tables_follow_the_tenant_pattern(migrated: None, owner_engine: Engine) -> None:
    """Every table with org_id has the standard policy and UNIQUE (org_id, id) for composite FKs."""
    with owner_engine.connect() as conn:
        tenant_tables = (
            conn.execute(
                text(
                    "SELECT table_name FROM information_schema.columns"
                    " WHERE table_schema = 'public' AND column_name = 'org_id'"
                )
            )
            .scalars()
            .all()
        )
        problems = []
        for table in tenant_tables:
            policy = conn.execute(
                text(
                    "SELECT qual, with_check FROM pg_policies"
                    " WHERE tablename = :t AND policyname = 'tenant_isolation' AND cmd = 'ALL'"
                ),
                {"t": table},
            ).one_or_none()
            if policy is None or policy != ("(org_id = app_current_org())",) * 2:
                problems.append(f"{table}: missing/unexpected tenant_isolation policy {policy}")
            has_unique = conn.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pg_constraint c"
                    " WHERE c.conrelid = CAST(:t AS regclass) AND c.contype IN ('u', 'p')"
                    " AND (SELECT array_agg(a.attname ORDER BY a.attname) FROM pg_attribute a"
                    "      WHERE a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey))"
                    "     = ARRAY['id', 'org_id']::name[])"
                ),
                {"t": table},
            ).scalar_one()
            if not has_unique:
                problems.append(f"{table}: missing UNIQUE (org_id, id)")
    assert tenant_tables, "expected at least one tenant table"
    assert problems == []


async def test_app_role_cannot_bypass_rls(sessionmaker: SM) -> None:
    async with sessionmaker() as s:
        row = (
            await s.execute(
                text(
                    "SELECT current_user, r.rolsuper, r.rolbypassrls,"
                    " (SELECT count(*) FROM pg_class c WHERE c.relowner = r.oid),"
                    " has_table_privilege('alembic_version', 'SELECT'),"
                    " has_schema_privilege('public', 'CREATE')"
                    " FROM pg_roles r WHERE r.rolname = current_user"
                )
            )
        ).one()
    assert tuple(row) == ("vp_app", False, False, 0, False, False)


def test_models_match_migrations(migrated: None, owner_engine: Engine) -> None:
    with owner_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []
