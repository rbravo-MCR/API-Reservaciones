from datetime import datetime, timedelta, timezone
from typing import Any

from app.application.interfaces.outbox_repo import OutboxEvent, OutboxRepo


class InMemoryOutboxRepo(OutboxRepo):
    def __init__(self) -> None:
        self._events: dict[int, OutboxEvent] = {}
        self._by_aggregate_event: dict[tuple[str, str], int] = {}
        self._next_id = 1

    async def enqueue(
        self,
        event_type: str,
        aggregate_type: str,
        aggregate_code: str,
        payload: dict[str, Any],
    ) -> OutboxEvent:
        now = datetime.now(timezone.utc)
        event = OutboxEvent(
            id=self._next_id,
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_code=aggregate_code,
            payload=payload,
            status="NEW",
            attempts=0,
            next_attempt_at=now,
        )
        self._events[self._next_id] = event
        self._by_aggregate_event[(aggregate_code, event_type)] = event.id
        self._next_id += 1
        return event

    async def claim(
        self,
        aggregate_code: str,
        event_type: str,
        locked_by: str,
        now: datetime,
        lock_ttl_seconds: int = 30,
    ) -> OutboxEvent | None:
        key = (aggregate_code, event_type)
        event_id = self._by_aggregate_event.get(key)
        if not event_id:
            return None
        event = self._events[event_id]
        if event.status not in {"NEW", "RETRY"}:
            return None
        if event.next_attempt_at and event.next_attempt_at > now:
            return None
        if event.lock_expires_at and event.lock_expires_at > now:
            return None

        event.locked_by = locked_by
        event.lock_expires_at = now + timedelta(seconds=lock_ttl_seconds)
        event.status = "IN_PROGRESS"
        self._events[event_id] = event
        return event

    async def mark_done(self, event_id: int) -> None:
        event = self._events.get(event_id)
        if not event:
            return
        event.status = "DONE"
        event.locked_by = None
        event.lock_expires_at = None
        self._events[event_id] = event

    async def mark_failed(
        self,
        event_id: int,
        attempts: int,
        aggregate_code: str,
        event_type: str,
        error_code: str | None,
        error_message: str | None,
    ) -> None:
        event = self._events.get(event_id)
        if not event:
            return
        event.status = "FAILED"
        event.attempts = attempts
        event.error_code = error_code
        event.error_message = error_message
        event.locked_by = None
        event.lock_expires_at = None
        self._events[event_id] = event

    async def mark_retry(
        self,
        event_id: int,
        attempts: int,
        next_attempt_at: datetime,
        error_code: str | None,
        error_message: str | None,
    ) -> None:
        event = self._events.get(event_id)
        if not event:
            return
        event.status = "RETRY"
        event.attempts = attempts
        event.next_attempt_at = next_attempt_at
        event.error_code = error_code
        event.error_message = error_message
        event.locked_by = None
        event.lock_expires_at = None
        self._events[event_id] = event
