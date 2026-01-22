import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import insert, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.interfaces.outbox_repo import OutboxEvent, OutboxRepo
from app.infrastructure.db.tables import outbox_dead_letters, outbox_events

logger = logging.getLogger(__name__)


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

    async def move_to_dlq(
        self,
        event: OutboxEvent,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """
        Move a permanently failed event to the Dead Letter Queue.

        This method:
        1. Inserts the event into outbox_dead_letters table
        2. Marks the original event as FAILED
        3. Logs the operation for monitoring

        The DLQ preserves all event data for manual intervention and analysis.
        """
        now = datetime.utcnow()

        # Extract reservation_code from payload if available
        reservation_code = event.payload.get("reservation_code") if event.payload else None

        # Insert into Dead Letter Queue
        dlq_stmt = insert(outbox_dead_letters).values(
            original_event_id=event.id,
            event_type=event.event_type,
            aggregate_type=event.aggregate_type,
            aggregate_id=0,  # Not used in current implementation
            reservation_code=reservation_code,
            payload=event.payload,
            error_code=error_code or event.error_code or "MAX_ATTEMPTS_EXCEEDED",
            error_message=error_message or event.error_message or "Event failed permanently after max attempts",
            attempts=event.attempts,
            moved_at=now,
            created_at=now,
        )
        await self._session.execute(dlq_stmt)

        # Mark original event as FAILED
        update_stmt = (
            update(outbox_events)
            .where(outbox_events.c.id == event.id)
            .values(
                status="FAILED",
                updated_at=now,
                locked_by=None,
                lock_expires_at=None,
            )
        )
        await self._session.execute(update_stmt)

        # Log for monitoring/alerting
        logger.warning(
            "Event moved to Dead Letter Queue - requires manual intervention",
            extra={
                "event_id": event.id,
                "event_type": event.event_type,
                "reservation_code": reservation_code,
                "attempts": event.attempts,
                "error_code": error_code or event.error_code,
            }
        )
