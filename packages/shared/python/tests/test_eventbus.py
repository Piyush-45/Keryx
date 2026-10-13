import json
import uuid
from typing import Any

import fakeredis
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from vp_shared.eventbus import STREAM, EventEmitter
from vp_shared.events import InvalidEventError, validate_event

TURN: dict[str, Any] = {
    "index": 0,
    "state_id": None,
    "user": None,
    "agent": {"text": "Namaste", "start_ms": 0, "end_ms": 800, "interrupted": False},
    "timings": {
        "eot_ms": None,
        "stt_final_ms": None,
        "llm_ttft_ms": None,
        "tts_ttfb_ms": 150,
        "v2v_ms": None,
    },
}


@pytest.fixture
def redis() -> fakeredis.FakeAsyncRedis:
    return fakeredis.FakeAsyncRedis()


async def _stream(redis: fakeredis.FakeAsyncRedis) -> list[dict[str, Any]]:
    entries: list[tuple[bytes, dict[bytes, bytes]]] = await redis.xrange(STREAM)  # type: ignore[assignment]
    return [json.loads(fields[b"event"]) for _, fields in entries]


async def test_emits_in_order_with_increasing_seq(redis: fakeredis.FakeAsyncRedis) -> None:
    org, call = uuid.uuid4(), uuid.uuid4()
    async with EventEmitter(redis, org_id=org, call_id=call) as em:
        for i in range(3):
            em.emit("turn", {**TURN, "index": i})
    events = await _stream(redis)
    assert [e["seq"] for e in events] == [0, 1, 2]
    assert [e["payload"]["index"] for e in events] == [0, 1, 2]
    assert {(e["org_id"], e["call_id"]) for e in events} == {(str(org), str(call))}
    assert all(validate_event(e) == [] for e in events)


async def test_start_seq_continues_after_persisted_events(redis: fakeredis.FakeAsyncRedis) -> None:
    async with EventEmitter(redis, org_id=uuid.uuid4(), call_id=uuid.uuid4(), start_seq=7) as em:
        em.emit("extraction.done", {"results": 1, "low_confidence": 0, "review_needed": False})
    assert [e["seq"] for e in await _stream(redis)] == [7]


async def test_invalid_event_raises_and_does_not_consume_seq(
    redis: fakeredis.FakeAsyncRedis,
) -> None:
    async with EventEmitter(redis, org_id=uuid.uuid4(), call_id=uuid.uuid4()) as em:
        with pytest.raises(InvalidEventError):
            em.emit("turn", {**TURN, "agent": None})
        em.emit("turn", TURN)
    assert [e["seq"] for e in await _stream(redis)] == [0]


class FlakyRedis:
    """Fails XADD while `down` is True; otherwise delegates to fakeredis."""

    def __init__(self, inner: fakeredis.FakeAsyncRedis) -> None:
        self.inner = inner
        self.down = True

    async def xadd(self, *args: Any, **kwargs: Any) -> Any:
        if self.down:
            raise RedisConnectionError("redis down")
        return await self.inner.xadd(*args, **kwargs)


async def test_buffers_while_redis_is_down_and_flushes_later(
    redis: fakeredis.FakeAsyncRedis,
) -> None:
    flaky = FlakyRedis(redis)
    em = EventEmitter(flaky, org_id=uuid.uuid4(), call_id=uuid.uuid4(), retry_delay_s=0.01)  # type: ignore[arg-type]
    em.start()
    em.emit("turn", TURN)  # does not raise or block
    em.emit("turn", {**TURN, "index": 1})
    assert em.pending == 2
    flaky.down = False
    await em.aclose()
    assert em.pending == 0
    assert [e["seq"] for e in await _stream(redis)] == [0, 1]


async def test_buffer_overflow_drops_oldest(redis: fakeredis.FakeAsyncRedis) -> None:
    flaky = FlakyRedis(redis)
    em = EventEmitter(flaky, org_id=uuid.uuid4(), call_id=uuid.uuid4(), max_buffer=2)  # type: ignore[arg-type]
    for i in range(3):
        em.emit("turn", {**TURN, "index": i})
    assert em.dropped == 1
    flaky.down = False
    await em.flush()
    assert [e["payload"]["index"] for e in await _stream(redis)] == [1, 2]


async def test_close_with_redis_down_does_not_raise(redis: fakeredis.FakeAsyncRedis) -> None:
    em = EventEmitter(FlakyRedis(redis), org_id=uuid.uuid4(), call_id=uuid.uuid4())  # type: ignore[arg-type]
    em.emit("turn", TURN)
    await em.aclose(timeout_s=0.1)
    assert em.pending == 1
