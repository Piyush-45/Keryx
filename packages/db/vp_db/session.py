"""Tenant-scoped sessions. The only way app code (API, workers) talks to the database.

Every transaction in a tenant session starts with
`set_config('app.current_org', <org_id>, true)`. `is_local=true` scopes the setting to the
transaction, so it can never leak to the next user of a pooled connection. RLS policies compare
`org_id` to `app_current_org()`; with no org set they match nothing (fail closed).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, SessionTransaction

_SET_ORG = text("SELECT set_config('app.current_org', :org_id, true)")


def create_engine(url: str, **kwargs: Any) -> AsyncEngine:
    """Engine for the app role (`DATABASE_URL`). Never use the migration/owner role here."""
    return create_async_engine(url, pool_pre_ping=True, **kwargs)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def tenant_session(
    sessionmaker: async_sessionmaker[AsyncSession], org_id: UUID
) -> AsyncIterator[AsyncSession]:
    """Yield a session whose every transaction is scoped to `org_id`; commits on clean exit.

    The org is re-applied at the start of each transaction, so `session.commit()` inside the
    block does not drop the scope.
    """
    org = str(org_id)

    async with sessionmaker() as session:

        @event.listens_for(session.sync_session, "after_begin")
        def _scope(_s: Session, _tx: SessionTransaction, connection: Connection) -> None:
            connection.execute(_SET_ORG, {"org_id": org})

        async with session.begin():
            yield session
