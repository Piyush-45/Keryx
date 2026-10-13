"""SQL for row-level security, used by Alembic migrations (decision 0005).

Every tenant-owned table: `op.execute` each statement from `enable_tenant_rls("<table>")`.
FORCE makes the table owner (vp_migrator) subject to RLS too; only the app role exists at runtime,
but this keeps owner-run scripts honest as well.
"""

import re
from typing import Literal

Command = Literal["ALL", "SELECT", "INSERT", "UPDATE", "DELETE"]

CURRENT_ORG = "app_current_org()"

# NULLIF: after a transaction that used set_config(..., true) ends, the setting reads as '' (not
# NULL) for the rest of the session, and ''::uuid would raise instead of matching nothing.
CREATE_CURRENT_ORG_FN = """
CREATE FUNCTION app_current_org() RETURNS uuid
LANGUAGE sql STABLE PARALLEL SAFE
AS $$ SELECT NULLIF(current_setting('app.current_org', true), '')::uuid $$
"""
DROP_CURRENT_ORG_FN = "DROP FUNCTION app_current_org()"

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def _ident(name: str) -> str:
    if not _IDENT.match(name):
        raise ValueError(f"unsafe SQL identifier: {name!r}")
    return name


def force_rls(table: str) -> list[str]:
    t = _ident(table)
    return [
        f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY",
    ]


def create_policy(
    table: str,
    name: str,
    *,
    command: Command = "ALL",
    using: str | None = None,
    with_check: str | None = None,
) -> str:
    sql = f"CREATE POLICY {_ident(name)} ON {_ident(table)} FOR {command}"
    if using is not None:
        sql += f" USING ({using})"
    if with_check is not None:
        sql += f" WITH CHECK ({with_check})"
    return sql


def enable_tenant_rls(table: str, *, org_column: str = "org_id") -> list[str]:
    """ENABLE + FORCE RLS and the standard policy: rows are visible/writable only in their org."""
    match = f"{_ident(org_column)} = {CURRENT_ORG}"
    return [
        *force_rls(table),
        create_policy(table, "tenant_isolation", using=match, with_check=match),
    ]
