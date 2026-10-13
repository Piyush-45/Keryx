"""Event transport: producers append to a Redis Stream; the persist consumer writes Postgres.

`EventEmitter.emit()` is synchronous and never awaits, so it can't stall the audio pipeline. A
background task flushes to Redis; while Redis is unreachable, events wait in a bounded buffer
(oldest dropped first, counted in `dropped`).
"""

import asyncio
import contextlib
import json
import logging
import uuid
from collections import deque
from types import TracebackType
from typing import Any, Self

from redis.asyncio import Redis
from redis.exceptions import RedisError

from vp_shared.events import EventType, InvalidEventError, build_event, validate_event

logger = logging.getLogger(__name__)

STREAM = "vp:events"
DEAD_LETTER_STREAM = "vp:events:dead"


class EventEmitter:
    def __init__(
        self,
        redis: Redis,
        *,
        org_id: uuid.UUID,
        call_id: uuid.UUID,
        start_seq: int = 0,
        stream: str = STREAM,
        max_buffer: int = 2000,
        retry_delay_s: float = 0.5,
    ) -> None:
        self._redis = redis
        self.org_id = org_id
        self.call_id = call_id
        self._next_seq = start_seq
        self._stream = stream
        self._buffer: deque[dict[str, Any]] = deque()
        self._max_buffer = max_buffer
        self._retry_delay_s = retry_delay_s
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self.dropped = 0

    def emit(self, type: EventType, payload: dict[str, Any]) -> dict[str, Any]:
        """Build, redact, validate and queue an event. Raises InvalidEventError on a bad event."""
        event = build_event(
            type, org_id=self.org_id, call_id=self.call_id, seq=self._next_seq, payload=payload
        )
        errors = validate_event(event)
        if errors:
            raise InvalidEventError(errors)
        self._next_seq += 1
        if len(self._buffer) >= self._max_buffer:
            self._buffer.popleft()
            self.dropped += 1
            logger.error("event buffer full; dropped oldest event for call %s", self.call_id)
        self._buffer.append(event)
        self._wake.set()
        return event

    @property
    def pending(self) -> int:
        return len(self._buffer)

    async def flush(self) -> None:
        """Send buffered events in order. An event leaves the buffer only after XADD succeeds."""
        while self._buffer:
            event = self._buffer[0]
            await self._redis.xadd(self._stream, {"event": json.dumps(event)})
            self._buffer.popleft()

    async def _run(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            try:
                await self.flush()
            except (RedisError, OSError) as exc:
                logger.warning("event flush failed (%s); %d buffered", exc, len(self._buffer))
                await asyncio.sleep(self._retry_delay_s)
                self._wake.set()

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name=f"events:{self.call_id}")

    async def aclose(self, timeout_s: float = 5.0) -> None:
        """Stop the background task and make a final, time-limited flush attempt."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        try:
            await asyncio.wait_for(self.flush(), timeout_s)
        except (TimeoutError, RedisError, OSError) as exc:
            logger.error("lost %d events for call %s at close: %s", self.pending, self.call_id, exc)

    async def __aenter__(self) -> Self:
        self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()
