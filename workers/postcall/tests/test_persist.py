"""Event persistence: Redis Stream -> call_events, as vp_app under RLS, against vp_test."""

import json
import uuid
from pathlib import Path
from typing import Any

import fakeredis
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from postcall.persist import GROUP, EventPersister
from vp_db.models import Call, CallEventRow
from vp_db.session import tenant_session
from vp_db.testing import make_call, make_org
from vp_shared.eventbus import DEAD_LETTER_STREAM, STREAM, EventEmitter

SM = async_sessionmaker[AsyncSession]
EXAMPLES = Path(__file__).resolve().parents[3] / "packages" / "shared" / "examples" / "events"


def payload(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((EXAMPLES / f"{name}.json").read_text())["payload"]
    return data


@pytest.fixture
def redis() -> fakeredis.FakeAsyncRedis:
    return fakeredis.FakeAsyncRedis()


async def persister(redis: fakeredis.FakeAsyncRedis, sm: SM, name: str = "p1") -> EventPersister:
    p = EventPersister(redis, sm, consumer=name)
    await p.ensure_group()
    return p


async def emit_call(redis: fakeredis.FakeAsyncRedis, org: uuid.UUID, call: uuid.UUID) -> None:
    async with EventEmitter(redis, org_id=org, call_id=call) as em:
        em.emit("call.started", payload("call_started"))
        em.emit("turn", payload("turn_greeting"))
        em.emit("turn", payload("turn_exchange"))
        em.emit("call.ended", payload("call_ended"))


async def stored(sm: SM, org: uuid.UUID) -> list[tuple[int, str]]:
    async with tenant_session(sm, org) as s:
        rows = await s.execute(select(CallEventRow.seq, CallEventRow.type).order_by("seq"))
        return [(r[0], r[1]) for r in rows]


async def dead_letters(redis: fakeredis.FakeAsyncRedis) -> list[dict[bytes, bytes]]:
    entries: list[tuple[bytes, dict[bytes, bytes]]] = await redis.xrange(DEAD_LETTER_STREAM)  # type: ignore[assignment]
    return [fields for _, fields in entries]


async def test_persists_events_and_updates_call(
    sessionmaker: SM, redis: fakeredis.FakeAsyncRedis
) -> None:
    org = await make_org(sessionmaker)
    call = await make_call(sessionmaker, org)
    p = await persister(redis, sessionmaker)
    await emit_call(redis, org, call)

    assert await p.process_new(block_ms=None) == 4
    assert await stored(sessionmaker, org) == [
        (0, "call.started"),
        (1, "turn"),
        (2, "turn"),
        (3, "call.ended"),
    ]
    async with tenant_session(sessionmaker, org) as s:
        row = (await s.execute(select(Call).where(Call.id == call))).scalar_one()
    assert (row.status, row.ended_by, row.duration_ms) == ("completed", "transfer", 31000)
    assert row.started_at is not None and row.ended_at is not None
    pending = await redis.xpending(STREAM, GROUP)
    assert pending["pending"] == 0


async def test_redelivery_is_idempotent(sessionmaker: SM, redis: fakeredis.FakeAsyncRedis) -> None:
    org = await make_org(sessionmaker)
    call = await make_call(sessionmaker, org)
    await emit_call(redis, org, call)
    await (await persister(redis, sessionmaker, "a")).process_new(block_ms=None)
    # Same events again on a fresh group (as if acks were lost).
    other = EventPersister(redis, sessionmaker, consumer="b", group="replay")
    await other.ensure_group()
    assert await other.process_new(block_ms=None) == 4
    assert len(await stored(sessionmaker, org)) == 4
    assert await dead_letters(redis) == []


async def test_event_for_another_orgs_call_is_dead_lettered(
    sessionmaker: SM, redis: fakeredis.FakeAsyncRedis
) -> None:
    a, b = await make_org(sessionmaker), await make_org(sessionmaker)
    call_b = await make_call(sessionmaker, b)
    p = await persister(redis, sessionmaker)
    async with EventEmitter(redis, org_id=a, call_id=call_b) as em:  # wrong org for this call
        em.emit("turn", payload("turn_greeting"))

    assert await p.process_new(block_ms=None) == 1  # acked via dead letter
    assert await stored(sessionmaker, a) == []
    assert await stored(sessionmaker, b) == []
    (dead,) = await dead_letters(redis)
    assert b"IntegrityError" in dead[b"reason"]


async def test_invalid_and_unparseable_messages_are_dead_lettered(
    sessionmaker: SM, redis: fakeredis.FakeAsyncRedis
) -> None:
    p = await persister(redis, sessionmaker)
    await redis.xadd(STREAM, {"event": "not json"})
    await redis.xadd(STREAM, {"event": json.dumps({"type": "turn", "payload": {}})})
    assert await p.process_new(block_ms=None) == 2
    reasons = [d[b"reason"] for d in await dead_letters(redis)]
    assert reasons[0] == b"unparseable JSON"
    assert b"'id' is a required property" in reasons[1]


async def test_events_are_isolated_between_orgs(
    sessionmaker: SM, redis: fakeredis.FakeAsyncRedis
) -> None:
    a, b = await make_org(sessionmaker), await make_org(sessionmaker)
    call_a, call_b = await make_call(sessionmaker, a), await make_call(sessionmaker, b)
    p = await persister(redis, sessionmaker)
    await emit_call(redis, a, call_a)
    await emit_call(redis, b, call_b)
    await p.process_new(block_ms=None)
    async with tenant_session(sessionmaker, a) as s:
        calls = (await s.execute(select(CallEventRow.call_id).distinct())).scalars().all()
        n_calls = (await s.execute(select(func.count()).select_from(Call))).scalar_one()
    assert calls == [call_a]
    assert n_calls == 1


async def test_reclaims_messages_a_crashed_consumer_never_acked(
    sessionmaker: SM, redis: fakeredis.FakeAsyncRedis
) -> None:
    org = await make_org(sessionmaker)
    call = await make_call(sessionmaker, org)
    await (await persister(redis, sessionmaker, "crashed")).ensure_group()
    await emit_call(redis, org, call)
    # "crashed" reads but never handles/acks.
    await redis.xreadgroup(GROUP, "crashed", {STREAM: ">"}, count=10)
    survivor = await persister(redis, sessionmaker, "survivor")
    assert await survivor.process_new(block_ms=None) == 0
    assert await survivor.reclaim_stale(min_idle_ms=0) == 4
    assert len(await stored(sessionmaker, org)) == 4
