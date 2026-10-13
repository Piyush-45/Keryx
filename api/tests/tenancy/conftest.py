"""Fixtures specific to the isolation tests. Shared DB fixtures come from vp_db.testing."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text

from vp_db.rls import enable_tenant_rls


@pytest.fixture(scope="session")
def fk_fixture_tables(migrated: None, owner_engine: Engine) -> Iterator[None]:
    """A parent/child tenant table pair with a composite (org_id, parent_id) FK.

    Built with enable_tenant_rls, exactly as a real migration would, so it also tests the helper.
    """
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE _rls_parent ("
                " id uuid PRIMARY KEY,"
                " org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,"
                " UNIQUE (org_id, id))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE _rls_child ("
                " id uuid PRIMARY KEY,"
                " org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,"
                " parent_id uuid NOT NULL,"
                " UNIQUE (org_id, id),"
                " FOREIGN KEY (org_id, parent_id) REFERENCES _rls_parent (org_id, id))"
            )
        )
        for table in ("_rls_parent", "_rls_child"):
            for stmt in enable_tenant_rls(table):
                conn.execute(text(stmt))
    yield
    with owner_engine.begin() as conn:
        conn.execute(text("DROP TABLE _rls_child, _rls_parent"))
