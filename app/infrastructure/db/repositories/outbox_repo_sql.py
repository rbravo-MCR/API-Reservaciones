from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import insert, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.interfaces.outbox_repo import OutboxEvent, OutboxRepo
from app.infrastructure.db.tables import outbox_events


class OutboxRepoSQL(OutboxRepo):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(
        self,
        event_type: str,
        aggregate_type: str,
        aggregate_code: str,
        payload: dict[str, Any],
    ) -> OutboxEvent:
        now = datetime.utcnow()
        stmt = insert(outbox_events).values(
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_code=aggregate_code,
            payload=payload,
            status="NEW",
            attempts=0,
            next_attempt_at=now,
            created_at=now,
        )
        result = await self._session.execute(stmt)
        event_id = result.inserted_primary_key[0]
        return OutboxEvent(
            id=event_id,
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_code=aggregate_code,
            payload=payload,
            status="NEW",
            attempts=0,
            next_attempt_at=now,
            locked_by=None,
            lock_expires_at=None,
        )

    async def claim(
        self,
        aggregate_code: str,
        event_type: str,
        locked_by: str,
        now: datetime,
        lock_ttl_seconds: int = 30,
    ) -> OutboxEvent | None:
        stmt = (
            update(outbox_events)
            .where(
                outbox_events.c.aggregate_code == aggregate_code,
                outbox_events.c.event_type == event_type,
                outbox_events.c.status.in_(("NEW", "RETRY")),
                or_(
                    outbox_events.c.next_attempt_at.is_(None),
                    outbox_events.c.next_attempt_at <= now,
                ),
                or_(
                    outbox_events.c.lock_expires_at.is_(None),
                    outbox_events.c.lock_expires_at <= now,
                ),
            )
            .values(
                locked_by=locked_by,
                locked_at=now,
                lock_expires_at=now + timedelta(seconds=lock_ttl_seconds),
                updated_at=now,
                status="IN_PROGRESS",
            )
            .returning(outbox_events)
        )
        result = await self._session.execute(stmt)
        row = result.first()
        if not row:
            return None
        data = row._mapping
        return OutboxEvent(
            id=data["id"],
            event_type=data["event_type"],
            aggregate_type=data["aggregate_type"],
            aggregate_code=data["aggregate_code"],
            payload=data["payload"],
            status=data["status"],
            attempts=data.get("attempts", 0),
            next_attempt_at=data.get("next_attempt_at"),
            locked_by=data.get("locked_by"),
            lock_expires_at=data.get("lock_expires_at"),
        )

    async def mark_done(self, event_id: int) -> None:
        now = datetime.utcnow()
        stmt = (
            update(outbox_events)
            .where(outbox_events.c.id == event_id)
            .values(status="DONE", locked_by=None, lock_expires_at=None, updated_at=now)
        )
        await self._session.execute(stmt)

    async def mark_failed(
        self,
        event_id: int,
        attempts: int,
        aggregate_code: str,
        event_type: str,
        error_code: str | None,
        error_message: str | None,
    ) -> None:
        now = datetime.utcnow()
        stmt = (
            update(outbox_events)
            .where(outbox_events.c.id == event_id)
            .values(
                status="FAILED",
                attempts=attempts,
                locked_by=None,
                lock_expires_at=None,
                updated_at=now,
            )
        )
        await self._session.execute(stmt)

    async def mark_retry(
        self,
        event_id: int,
        attempts: int,
        next_attempt_at: datetime,
        error_code: str | None,
        error_message: str | None,
    ) -> None:
        now = datetime.utcnow()
        stmt = (
            update(outbox_events)
            .where(outbox_events.c.id == event_id)
            .values(
                status="RETRY",
                attempts=attempts,
                next_attempt_at=next_attempt_at,
                locked_by=None,
                lock_expires_at=None,
                updated_at=now,
            )
        )
        await self._session.execute(stmt)
