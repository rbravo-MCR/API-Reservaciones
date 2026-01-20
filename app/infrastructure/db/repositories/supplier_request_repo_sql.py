from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.interfaces.supplier_request_repo import (
    SupplierRequestRecord,
    SupplierRequestRepo,
)
from app.infrastructure.db.tables import reservation_supplier_requests, reservations


class SupplierRequestRepoSQL(SupplierRequestRepo):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _reservation_id(self, reservation_code: str) -> int | None:
        stmt = select(reservations.c.id).where(reservations.c.reservation_code == reservation_code)
        result = await self._session.execute(stmt)
        row = result.first()
        return row[0] if row else None

    async def create_in_progress(
        self,
        reservation_code: str,
        supplier_id: int,
        request_type: str,
        idem_key: str | None,
        attempt: int,
    ) -> SupplierRequestRecord:
        reservation_id = await self._reservation_id(reservation_code)
        stmt = insert(reservation_supplier_requests).values(
            reservation_id=reservation_id,
            reservation_code=reservation_code,
            supplier_id=supplier_id,
            request_type=request_type,
            idem_key=idem_key,
            attempt=attempt,
            status="IN_PROGRESS",
        )
        result = await self._session.execute(stmt)
        req_id = result.inserted_primary_key[0]
        return SupplierRequestRecord(
            id=req_id,
            reservation_code=reservation_code,
            supplier_id=supplier_id,
            request_type=request_type,
            idem_key=idem_key,
            attempt=attempt,
            status="IN_PROGRESS",
        )

    async def mark_success(
        self,
        request_id: int,
        response_payload: dict[str, Any] | None,
        supplier_reservation_code: str,
    ) -> SupplierRequestRecord:
        stmt = (
            update(reservation_supplier_requests)
            .where(reservation_supplier_requests.c.id == request_id)
            .values(status="SUCCESS", response_payload=response_payload)
        )
        await self._session.execute(stmt)
        return await self._fetch(request_id)

    async def mark_failed(
        self,
        request_id: int,
        error_code: str | None,
        error_message: str | None,
        http_status: int | None,
        response_payload: dict[str, Any] | None,
    ) -> SupplierRequestRecord:
        stmt = (
            update(reservation_supplier_requests)
            .where(reservation_supplier_requests.c.id == request_id)
            .values(
                status="FAILED",
                error_code=error_code,
                error_message=error_message,
                http_status=http_status,
                response_payload=response_payload,
            )
        )
        await self._session.execute(stmt)
        return await self._fetch(request_id)

    async def _fetch(self, request_id: int) -> SupplierRequestRecord:
        stmt = select(reservation_supplier_requests).where(
            reservation_supplier_requests.c.id == request_id
        )
        result = await self._session.execute(stmt)
        row = result.mappings().first()
        if not row:
            raise ValueError("Supplier request not found")
        return SupplierRequestRecord(
            id=row["id"],
            reservation_code=row.get("reservation_code") or "",
            supplier_id=row.get("supplier_id") or 0,
            request_type=row["request_type"],
            idem_key=row.get("idem_key"),
            attempt=row.get("attempt", 0),
            status=row["status"],
            response_payload=row.get("response_payload"),
            error_code=row.get("error_code"),
            error_message=row.get("error_message"),
            http_status=row.get("http_status"),
        )
