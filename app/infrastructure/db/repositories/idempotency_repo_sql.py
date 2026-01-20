from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.interfaces.idempotency_repo import IdempotencyRecord, IdempotencyRepo
from app.infrastructure.db.tables import idempotency_keys


class IdempotencyRepoSQL(IdempotencyRepo):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, scope: str, idem_key: str) -> IdempotencyRecord | None:
        stmt = (
            select(idempotency_keys)
            .where(
                idempotency_keys.c.scope == scope,
                idempotency_keys.c.idem_key == idem_key,
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        row = result.mappings().first()
        if not row:
            return None
        return IdempotencyRecord(
            scope=row["scope"],
            idem_key=row["idem_key"],
            request_hash=row["request_hash"],
            response_json=row["response_json"] or {},
            http_status=row.get("http_status", 200) or 200,
            reference_reservation_code=row.get("reference_reservation_code"),
        )

    async def save(self, record: IdempotencyRecord) -> None:
        stmt = insert(idempotency_keys).values(
            scope=record.scope,
            idem_key=record.idem_key,
            request_hash=record.request_hash,
            response_json=record.response_json,
            http_status=record.http_status,
            reference_reservation_code=record.reference_reservation_code,
        )
        await self._session.execute(stmt)
