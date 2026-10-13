"""Structural guards: catch a new table or role setup that would silently weaken isolation."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, Engine, text
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
                    " has_schema_privilege('public', 'CREATE'),"
                    " pg_has_role(current_user, 'vp_resolver', 'MEMBER')"
                    " FROM pg_roles r WHERE r.rolname = current_user"
                )
            )
        ).one()
    assert tuple(row) == ("vp_app", False, False, 0, False, False, False)


def test_models_match_migrations(migrated: None, owner_engine: Engine) -> None:
    with owner_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


# --- resolver functions (decision 0005) ---

# "pg_catalog, public" or tighter. pg_temp, if listed, must come last.
_ALLOWED_PATH_ENTRIES = {"pg_catalog", "public", "pg_temp"}

_RESOLVER_CANDIDATES = text(
    "SELECT p.oid::regprocedure::text,"
    " p.prosecdef,"
    " pg_get_userbyid(p.proowner),"
    " (SELECT substr(c, length('search_path=') + 1) FROM unnest(p.proconfig) c"
    "   WHERE c LIKE 'search_path=%'),"
    " EXISTS (SELECT 1 FROM aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a"
    "   WHERE a.grantee = 0 AND a.privilege_type = 'EXECUTE'),"
    " has_function_privilege('vp_app', p.oid, 'EXECUTE')"
    " FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace"
    " WHERE n.nspname = 'public'"
    "   AND (p.prosecdef OR p.proowner = (SELECT oid FROM pg_roles WHERE rolname = 'vp_resolver'))"
)


def _search_path_ok(value: str | None) -> bool:
    if not value:
        return False
    entries = [e.strip().strip('"') for e in value.split(",")]
    return (
        entries[0] == "pg_catalog"
        and set(entries) <= _ALLOWED_PATH_ENTRIES
        and ("pg_temp" not in entries or entries[-1] == "pg_temp")
    )


def resolver_violations(conn: Connection) -> list[str]:
    """Every SECURITY DEFINER function, and everything owned by vp_resolver, must be a locked-down
    resolver: SECURITY DEFINER, owned by vp_resolver, pinned search_path, not executable by
    PUBLIC, executable by vp_app."""
    problems = []
    for fn, secdef, owner, path, public_exec, app_exec in conn.execute(_RESOLVER_CANDIDATES):
        if not secdef:
            problems.append(f"{fn}: owned by vp_resolver but not SECURITY DEFINER")
        if owner != "vp_resolver":
            problems.append(f"{fn}: SECURITY DEFINER but owned by {owner}, not vp_resolver")
        if not _search_path_ok(path):
            problems.append(f"{fn}: search_path {path!r} is not pg_catalog, public (or tighter)")
        if public_exec:
            problems.append(f"{fn}: EXECUTE granted to PUBLIC")
        if not app_exec:
            problems.append(f"{fn}: vp_app cannot EXECUTE it")
    return problems


def test_resolver_functions_are_locked_down(migrated: None, owner_engine: Engine) -> None:
    with owner_engine.connect() as conn:
        assert resolver_violations(conn) == []


def test_resolver_guard_catches_each_mistake(migrated: None, owner_engine: Engine) -> None:
    """Exercise the guard on throwaway functions (rolled back), one per mistake."""

    def fn(name: str, *, definer: bool = True, path: str | None = "pg_catalog, public") -> str:
        return (
            f"CREATE FUNCTION {name}(key text) RETURNS uuid LANGUAGE sql STABLE STRICT"
            + (" SECURITY DEFINER" if definer else "")
            + (f" SET search_path = {path}" if path else "")
            + " AS $$ SELECT NULL::uuid $$"
        )

    def lock_down(name: str, *, owner: str = "vp_resolver", public: bool = False) -> list[str]:
        return [
            f"REVOKE EXECUTE ON FUNCTION {name}(text) FROM PUBLIC" if not public else "SELECT 1",
            f"GRANT EXECUTE ON FUNCTION {name}(text) TO vp_app",
            f"ALTER FUNCTION {name}(text) OWNER TO {owner}",
        ]

    cases = {
        "_guard_ok": [fn("_guard_ok"), *lock_down("_guard_ok")],
        "_guard_ok_tight": [
            fn("_guard_ok_tight", path="pg_catalog"),
            *lock_down("_guard_ok_tight"),
        ],
        "_guard_no_path": [fn("_guard_no_path", path=None), *lock_down("_guard_no_path")],
        "_guard_public_first": [
            fn("_guard_public_first", path="public, pg_catalog"),
            *lock_down("_guard_public_first"),
        ],
        "_guard_public_exec": [
            fn("_guard_public_exec"),
            *lock_down("_guard_public_exec", public=True),
        ],
        "_guard_wrong_owner": [
            fn("_guard_wrong_owner"),
            *lock_down("_guard_wrong_owner", owner="vp_migrator"),
        ],
        "_guard_invoker": [fn("_guard_invoker", definer=False), *lock_down("_guard_invoker")],
    }
    with owner_engine.connect() as conn, conn.begin() as tx:
        for statements in cases.values():
            for stmt in statements:
                conn.execute(text(stmt))
        problems = resolver_violations(conn)
        tx.rollback()

    flagged = {p.split("(")[0] for p in problems}
    assert flagged == set(cases) - {"_guard_ok", "_guard_ok_tight"}
    assert any("_guard_no_path" in p and "search_path None" in p for p in problems)
    assert any("_guard_public_first" in p and "search_path" in p for p in problems)
    assert any("_guard_public_exec" in p and "PUBLIC" in p for p in problems)
    assert any("_guard_wrong_owner" in p and "owned by vp_migrator" in p for p in problems)
    assert any("_guard_invoker" in p and "not SECURITY DEFINER" in p for p in problems)
