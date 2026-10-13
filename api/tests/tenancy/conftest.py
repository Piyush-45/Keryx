"""Fixtures for tenant-isolation tests against the test database (vp_test).

Schema is built with Alembic as the owner role; every assertion runs as the app role (vp_app)
through vp_db.session.tenant_session, i.e. the same path production code uses.
"""

import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from vp_db.models import Membership, Organization, User
from vp_db.rls import enable_tenant_rls
from vp_db.session import create_engine as create_app_engine
from vp_db.session import create_sessionmaker, tenant_session

API_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = API_DIR.parent


class DbTestSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    test_database_url: str
    test_migration_database_url: str


@pytest.fixture(scope="session")
def db_settings() -> DbTestSettings:
    try:
        return DbTestSettings()
    except Exception as exc:
        pytest.fail(
            "TEST_DATABASE_URL / TEST_MIGRATION_DATABASE_URL missing "
            f"(see docs/local-setup.md): {exc}"
        )


@pytest.fixture(scope="session")
def owner_engine(db_settings: DbTestSettings) -> Iterator[Engine]:
    engine = create_engine(db_settings.test_migration_database_url, poolclass=NullPool)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def migrated(db_settings: DbTestSettings, owner_engine: Engine) -> None:
    """Rebuild the test schema from scratch: exercises downgrade and upgrade every run."""
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_settings.test_migration_database_url)
    with owner_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS _rls_child, _rls_parent"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


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


@pytest.fixture
async def sessionmaker(
    migrated: None, db_settings: DbTestSettings
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_app_engine(db_settings.test_database_url, poolclass=NullPool)
    yield create_sessionmaker(engine)
    await engine.dispose()


async def make_org(sm: async_sessionmaker[AsyncSession], name: str = "Org") -> uuid.UUID:
    """Create an org the way the app will: scope to the new id, then insert."""
    org_id = uuid.uuid4()
    async with tenant_session(sm, org_id) as s:
        s.add(Organization(id=org_id, name=name))
    return org_id


async def add_member(
    sm: async_sessionmaker[AsyncSession],
    org_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
    role: str = "member",
) -> uuid.UUID:
    """Add a user to an org (creating the user if `user_id` is None). Returns the user id."""
    async with tenant_session(sm, org_id) as s:
        if user_id is None:
            user_id = uuid.uuid4()
            s.add(User(id=user_id, email=f"{user_id}@example.com"))
            await s.flush()
        s.add(Membership(org_id=org_id, user_id=user_id, role=role))
    return user_id
