"""Persist call events from the Redis Stream into Postgres (decision 0007).

At-least-once: a message is acked only after its event is stored (or dead-lettered). Redelivered
events are ignored by primary key (the event id). Every write goes through tenant_session for the
event's org; the composite FK (org_id, call_id) -> calls rejects an event whose org doesn't own the
call, so a wrong org_id can't attach events to another tenant's call.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, cast

from redis.asyncio import Redis
from redis.exceptions import ResponseError
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError, IntegrityError, InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from vp_db.models import Call, CallEventRow
from vp_db.session import tenant_session
from vp_shared.eventbus import DEAD_LETTER_STREAM, STREAM
from vp_shared.events import validate_event

logger = logging.getLogger(__name__)

GROUP = "persist"

Message = tuple[bytes, dict[bytes, bytes]]


class EventPersister:
    def __init__(
        self,
        redis: Redis,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        consumer: str,
        stream: str = STREAM,
        group: str = GROUP,
        dead_letter_stream: str = DEAD_LETTER_STREAM,
    ) -> None:
        self._redis = redis
        self._sm = sessionmaker
        self._consumer = consumer
        self._stream = stream
        self._group = group
        self._dead = dead_letter_stream

    async def ensure_group(self) -> None:
        try:
            await self._redis.xgroup_create(self._stream, self._group, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def process_new(self, *, count: int = 100, block_ms: int | None = 1000) -> int:
        """Read and handle new messages. Returns how many were acked."""
        reply = cast(
            list[tuple[bytes, list[Message]]] | None,
            await self._redis.xreadgroup(
                self._group, self._consumer, {self._stream: ">"}, count=count, block=block_ms
            ),
        )
        return await self._handle_all([m for _, messages in reply or [] for m in messages])

    async def reclaim_stale(self, *, min_idle_ms: int = 60_000, count: int = 100) -> int:
        """Take over messages another consumer read but never acked (crash, DB outage)."""
        _, messages, *_ = await self._redis.xautoclaim(
            self._stream, self._group, self._consumer, min_idle_ms, "0-0", count=count
        )
        return await self._handle_all(messages)

    async def _handle_all(self, messages: list[Message]) -> int:
        acked = 0
        for message_id, fields in messages:
            if await self._handle(message_id, fields):
                acked += 1
        return acked

    async def _handle(self, message_id: bytes, fields: dict[bytes, bytes]) -> bool:
        raw = fields.get(b"event", b"")
        try:
            event = json.loads(raw)
        except ValueError:
            return await self._dead_letter(message_id, raw, "unparseable JSON")
        errors = validate_event(event)
        if errors:
            return await self._dead_letter(message_id, raw, "; ".join(map(str, errors)))
        try:
            await self._store(event)
        except (OperationalError, InterfaceError) as exc:
            # Transient (DB down, connection lost): leave unacked; reclaim_stale retries it.
            logger.warning("event %s not stored, will retry: %s", event["id"], exc)
            return False
        except (IntegrityError, DBAPIError) as exc:
            # Permanent: unknown call, call owned by another org, seq clash, RLS violation.
            return await self._dead_letter(message_id, raw, f"{type(exc).__name__}: {exc.orig}")
        await self._redis.xack(self._stream, self._group, message_id)
        return True

    async def _store(self, event: dict[str, Any]) -> None:
        org_id = uuid.UUID(event["org_id"])
        call_id = uuid.UUID(event["call_id"])
        ts = datetime.fromisoformat(event["ts"])
        async with tenant_session(self._sm, org_id) as s:
            result = await s.execute(
                insert(CallEventRow)
                .values(
                    id=uuid.UUID(event["id"]),
                    org_id=org_id,
                    call_id=call_id,
                    seq=event["seq"],
                    type=event["type"],
                    v=event["v"],
                    ts=ts,
                    payload=event["payload"],
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )
            if result.rowcount == 0:  # type: ignore[attr-defined]
                return  # redelivery of an event we already stored
            payload = event["payload"]
            calls = update(Call).where(Call.id == call_id)
            if event["type"] == "call.started":
                await s.execute(calls.values(status="in_progress", started_at=ts))
            elif event["type"] == "call.ended":
                status = "failed" if payload["ended_by"] == "error" else "completed"
                await s.execute(
                    calls.values(
                        status=status,
                        ended_at=ts,
                        ended_by=payload["ended_by"],
                        duration_ms=payload["duration_ms"],
                    )
                )

    async def _dead_letter(self, message_id: bytes, raw: bytes, reason: str) -> bool:
        logger.error("dead-lettering event message %s: %s", message_id, reason)
        await self._redis.xadd(
            self._dead, {"event": raw, "reason": reason[:2000], "source_id": message_id}
        )
        await self._redis.xack(self._stream, self._group, message_id)
        return True
