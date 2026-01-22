from app.application.interfaces.supplier_request_repo import (
    SupplierRequestRecord,
    SupplierRequestRepo,
)


class InMemorySupplierRequestRepo(SupplierRequestRepo):
    def __init__(self) -> None:
        self._records: dict[int, SupplierRequestRecord] = {}
        self._by_reservation: dict[str, list[int]] = {}
        self._next_id = 1

    async def create_in_progress(
        self,
        reservation_code: str,
        supplier_id: int,
        request_type: str,
        idem_key: str | None,
        attempt: int,
    ) -> SupplierRequestRecord:
        record = SupplierRequestRecord(
            id=self._next_id,
            reservation_code=reservation_code,
            supplier_id=supplier_id,
            request_type=request_type,
            idem_key=idem_key,
            attempt=attempt,
            status="IN_PROGRESS",
        )
        self._records[record.id] = record
        self._by_reservation.setdefault(reservation_code, []).append(record.id)
        self._next_id += 1
        return record

    async def mark_success(
        self,
        request_id: int,
        response_payload: dict | None,
        supplier_reservation_code: str,
    ) -> SupplierRequestRecord:
        record = self._records[request_id]
        record.status = "SUCCESS"
        record.response_payload = response_payload
        record.error_code = None
        record.error_message = None
        record.http_status = None
        # supplier_reservation_code stored in reservation repo; still keep payload here
        return record

    async def mark_failed(
        self,
        request_id: int,
        error_code: str | None,
        error_message: str | None,
        http_status: int | None,
        response_payload: dict | None,
    ) -> SupplierRequestRecord:
        record = self._records[request_id]
        record.status = "FAILED"
        record.error_code = error_code
        record.error_message = error_message
        record.http_status = http_status
        record.response_payload = response_payload
        return record
