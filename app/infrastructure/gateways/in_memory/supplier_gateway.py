from typing import Any
from uuid import uuid4

from app.application.interfaces.supplier_gateway import SupplierBookingResult, SupplierGateway


class StubSupplierGateway(SupplierGateway):
    async def book(
        self, reservation_code: str, idem_key: str, reservation_snapshot=None
    ) -> SupplierBookingResult:
        # Always succeeds for now
        return SupplierBookingResult(
            status="SUCCESS",
            supplier_reservation_code=f"SUP-{uuid4().hex[:8].upper()}",
            payload={
                "echo_reservation_code": reservation_code,
                "idem_key": idem_key,
                "confirmed_at": "2026-01-01T00:00:00",
            },
        )

    async def confirm_booking(self, reservation_code: str, details: dict[str, Any]) -> str:
        result = await self.book(reservation_code, f"compat-{reservation_code}", details)
        return result.supplier_reservation_code or "STUB-CONF"
