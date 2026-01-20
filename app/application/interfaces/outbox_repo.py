from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class OutboxEvent:
    id: int
    event_type: str
    aggregate_type: str
    aggregate_code: str
    payload: dict[str, Any]
    status: str
    attempts: int = 0
    next_attempt_at: datetime | None = None
    locked_by: str | None = None
    lock_expires_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


class OutboxRepo:
    async def enqueue(
        self,
        event_type: str,
        aggregate_type: str,
        aggregate_code: str,
        payload: dict[str, Any],
    ) -> OutboxEvent:
        raise NotImplementedError

    async def claim(
        self,
        aggregate_code: str,
        event_type: str,
        locked_by: str,
        now: datetime,
        lock_ttl_seconds: int = 30,
    ) -> OutboxEvent | None:
        raise NotImplementedError

    async def mark_done(self, event_id: int) -> None:
        raise NotImplementedError

    async def mark_retry(
        self,
        event_id: int,
        attempts: int,
        next_attempt_at: datetime,
        error_code: str | None,
        error_message: str | None,
    ) -> None:
        raise NotImplementedError

    async def mark_failed(
        self,
        event_id: int,
        attempts: int,
        aggregate_code: str,
        event_type: str,
        error_code: str | None,
        error_message: str | None,
    ) -> None:
        raise NotImplementedError
