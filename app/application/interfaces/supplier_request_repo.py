from dataclasses import dataclass
from typing import Any


@dataclass
class SupplierRequestRecord:
    id: int
    reservation_code: str
    supplier_id: int
    request_type: str
    idem_key: str | None
    attempt: int
    status: str
    response_payload: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    http_status: int | None = None


class SupplierRequestRepo:
    async def create_in_progress(
        self,
        reservation_code: str,
        supplier_id: int,
        request_type: str,
        idem_key: str | None,
        attempt: int,
    ) -> SupplierRequestRecord:
        raise NotImplementedError

    async def mark_success(
        self,
        request_id: int,
        response_payload: dict[str, Any] | None,
        supplier_reservation_code: str,
    ) -> SupplierRequestRecord:
        raise NotImplementedError

    async def mark_failed(
        self,
        request_id: int,
        error_code: str | None,
        error_message: str | None,
        http_status: int | None,
        response_payload: dict[str, Any] | None,
    ) -> SupplierRequestRecord:
        raise NotImplementedError
