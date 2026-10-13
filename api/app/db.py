"""API database access. Request handlers get a tenant session; there is no unscoped session."""

from functools import cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.settings import get_settings
from vp_db.session import create_engine, create_sessionmaker


@cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Sessionmaker bound to the app role (vp_app). Use with `vp_db.session.tenant_session`."""
    return create_sessionmaker(create_engine(get_settings().database_url))
