"""Tenant isolation: one org can never read or write another org's rows (decision 0002/0005)."""

import uuid

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import AsyncAdaptedQueuePool

from vp_db.models import Membership, Organization, User
from vp_db.session import create_engine, create_sessionmaker, tenant_session

from .conftest import DbTestSettings, add_member, make_org

SM = async_sessionmaker[AsyncSession]
RLS_VIOLATION = "row-level security policy"


async def _count(s: AsyncSession, model: type[object]) -> int:
    return (await s.execute(select(func.count()).select_from(model))).scalar_one()


# --- organizations ---


async def test_org_sees_only_itself(sessionmaker: SM) -> None:
    a, b = await make_org(sessionmaker, "A"), await make_org(sessionmaker, "B")
    async with tenant_session(sessionmaker, a) as s:
        ids = (await s.execute(select(Organization.id))).scalars().all()
    assert ids == [a]
    assert b not in ids


async def test_cannot_create_org_outside_own_scope(sessionmaker: SM) -> None:
    a = await make_org(sessionmaker)
    with pytest.raises(DBAPIError, match=RLS_VIOLATION):
        async with tenant_session(sessionmaker, a) as s:
            s.add(Organization(id=uuid.uuid4(), name="Sneaky"))


async def test_org_with_members_cannot_be_deleted(sessionmaker: SM) -> None:
    a = await make_org(sessionmaker)
    await add_member(sessionmaker, a)
    with pytest.raises(IntegrityError):
        async with tenant_session(sessionmaker, a) as s:
            await s.execute(text("DELETE FROM organizations WHERE id = :id"), {"id": a})


# --- memberships (standard tenant table) ---


async def test_memberships_are_isolated(sessionmaker: SM) -> None:
    a, b = await make_org(sessionmaker), await make_org(sessionmaker)
    await add_member(sessionmaker, a)
    await add_member(sessionmaker, b)
    await add_member(sessionmaker, b)
    async with tenant_session(sessionmaker, a) as s:
        orgs = set((await s.execute(select(Membership.org_id))).scalars())
        assert orgs == {a}
        assert await _count(s, Membership) == 1


async def test_cannot_insert_row_for_another_org(sessionmaker: SM) -> None:
    a, b = await make_org(sessionmaker), await make_org(sessionmaker)
    user = await add_member(sessionmaker, a)
    with pytest.raises(DBAPIError, match=RLS_VIOLATION):
        async with tenant_session(sessionmaker, a) as s:
            s.add(Membership(org_id=b, user_id=user, role="member"))


async def test_cannot_move_row_to_another_org(sessionmaker: SM) -> None:
    a, b = await make_org(sessionmaker), await make_org(sessionmaker)
    await add_member(sessionmaker, a)
    with pytest.raises(DBAPIError, match=RLS_VIOLATION):
        async with tenant_session(sessionmaker, a) as s:
            await s.execute(update(Membership).values(org_id=b))


async def test_cannot_update_or_delete_other_orgs_rows(sessionmaker: SM) -> None:
    a, b = await make_org(sessionmaker), await make_org(sessionmaker)
    await add_member(sessionmaker, b, role="member")
    async with tenant_session(sessionmaker, a) as s:
        updated = await s.execute(
            update(Membership).where(Membership.org_id == b).values(role="owner")
        )
        deleted = await s.execute(text("DELETE FROM memberships WHERE org_id = :b"), {"b": b})
    assert updated.rowcount == 0  # type: ignore[attr-defined]
    assert deleted.rowcount == 0  # type: ignore[attr-defined]
    async with tenant_session(sessionmaker, b) as s:
        roles = (await s.execute(select(Membership.role))).scalars().all()
    assert roles == ["member"]


# --- users (global identity, visible via membership) ---


async def test_user_visible_only_in_orgs_they_belong_to(sessionmaker: SM) -> None:
    a, b = await make_org(sessionmaker), await make_org(sessionmaker)
    user = await add_member(sessionmaker, a)
    async with tenant_session(sessionmaker, a) as s:
        assert (await s.execute(select(User.id))).scalars().all() == [user]
    async with tenant_session(sessionmaker, b) as s:
        assert await _count(s, User) == 0

    await add_member(sessionmaker, b, user_id=user)
    async with tenant_session(sessionmaker, b) as s:
        assert (await s.execute(select(User.id))).scalars().all() == [user]


async def test_users_cannot_be_updated_or_deleted_yet(sessionmaker: SM) -> None:
    a = await make_org(sessionmaker)
    await add_member(sessionmaker, a)
    async with tenant_session(sessionmaker, a) as s:
        updated = await s.execute(update(User).values(name="renamed"))
        deleted = await s.execute(text("DELETE FROM users"))
    assert updated.rowcount == 0  # type: ignore[attr-defined]
    assert deleted.rowcount == 0  # type: ignore[attr-defined]


# --- no org set: fail closed ---


async def test_unscoped_session_sees_nothing_and_cannot_write(sessionmaker: SM) -> None:
    a = await make_org(sessionmaker)
    await add_member(sessionmaker, a)
    async with sessionmaker() as s:
        assert await _count(s, Organization) == 0
        assert await _count(s, Membership) == 0
        assert await _count(s, User) == 0
    with pytest.raises(DBAPIError, match=RLS_VIOLATION):
        async with sessionmaker() as s, s.begin():
            s.add(User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@example.com"))


# --- scope lifetime ---


async def test_scope_does_not_leak_to_next_user_of_connection(
    migrated: None, db_settings: DbTestSettings
) -> None:
    engine = create_engine(
        db_settings.test_database_url, poolclass=AsyncAdaptedQueuePool, pool_size=1, max_overflow=0
    )
    sm = create_sessionmaker(engine)
    try:
        a = await make_org(sm)
        await add_member(sm, a)
        async with tenant_session(sm, a) as s:
            pid = (await s.execute(text("SELECT pg_backend_pid()"))).scalar_one()
            assert await _count(s, Membership) == 1
        async with sm() as s:
            row = (
                await s.execute(
                    text(
                        "SELECT pg_backend_pid(), current_setting('app.current_org', true),"
                        " app_current_org()"
                    )
                )
            ).one()
            assert row[0] == pid  # same pooled connection
            assert row[1] == ""  # setting was transaction-local
            assert row[2] is None
            assert await _count(s, Membership) == 0
    finally:
        await engine.dispose()


async def test_scope_survives_commit_inside_tenant_session(sessionmaker: SM) -> None:
    a = await make_org(sessionmaker)
    async with tenant_session(sessionmaker, a) as s:
        user = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@example.com")
        s.add(user)
        await s.flush()
        s.add(Membership(org_id=a, user_id=user.id, role="owner"))
        await s.commit()
        # New transaction after commit: still scoped to `a`.
        assert await _count(s, Membership) == 1
        assert await _count(s, Organization) == 1


# --- composite FKs block cross-tenant references ---


async def test_composite_fk_blocks_reference_to_other_orgs_row(
    sessionmaker: SM, fk_fixture_tables: None
) -> None:
    a, b = await make_org(sessionmaker), await make_org(sessionmaker)
    parent_b = uuid.uuid4()
    async with tenant_session(sessionmaker, b) as s:
        await s.execute(
            text("INSERT INTO _rls_parent (id, org_id) VALUES (:id, :org)"),
            {"id": parent_b, "org": b},
        )
    with pytest.raises(IntegrityError, match="_rls_child"):
        async with tenant_session(sessionmaker, a) as s:
            await s.execute(
                text("INSERT INTO _rls_child (id, org_id, parent_id) VALUES (:id, :org, :p)"),
                {"id": uuid.uuid4(), "org": a, "p": parent_b},
            )


async def test_enable_tenant_rls_helper_isolates_new_tables(
    sessionmaker: SM, fk_fixture_tables: None
) -> None:
    a, b = await make_org(sessionmaker), await make_org(sessionmaker)
    async with tenant_session(sessionmaker, b) as s:
        await s.execute(
            text("INSERT INTO _rls_parent (id, org_id) VALUES (:id, :org)"),
            {"id": uuid.uuid4(), "org": b},
        )
    async with tenant_session(sessionmaker, a) as s:
        visible = (
            await s.execute(text("SELECT count(*) FROM _rls_parent WHERE org_id = :b"), {"b": b})
        ).scalar_one()
    assert visible == 0
