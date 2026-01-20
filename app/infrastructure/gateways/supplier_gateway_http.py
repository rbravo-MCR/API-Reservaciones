import json
from typing import Any

import httpx

from app.application.interfaces.supplier_gateway import SupplierBookingResult, SupplierGateway


class SupplierGatewayHTTP(SupplierGateway):
    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def book(
        self, reservation_code: str, idem_key: str, reservation_snapshot=None
    ) -> SupplierBookingResult:
        url = f"{self._base_url}/book"
        headers = {"Idempotency-Key": idem_key}
        payload: dict[str, Any] = {"reservation_code": reservation_code, "idem_key": idem_key}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:  # pragma: no cover - real gateway path
            return SupplierBookingResult(
                status="FAILED",
                supplier_reservation_code=None,
                payload=None,
                error_code="TIMEOUT",
                error_message=str(exc),
                http_status=None,
            )
        except httpx.HTTPError as exc:  # pragma: no cover - real gateway path
            return SupplierBookingResult(
                status="FAILED",
                supplier_reservation_code=None,
                payload=None,
                error_code="HTTP_ERROR",
                error_message=str(exc),
                http_status=None,
            )

        body: dict[str, Any] | None = None
        try:
            body = response.json()
        except json.JSONDecodeError:
            body = None

        if 200 <= response.status_code < 300:
            supplier_code = None
            if isinstance(body, dict):
                supplier_code = body.get("supplier_reservation_code") or body.get(
                    "reservation_code"
                )
            return SupplierBookingResult(
                status="SUCCESS",
                supplier_reservation_code=supplier_code,
                payload=body,
                http_status=response.status_code,
            )

        return SupplierBookingResult(
            status="FAILED",
            supplier_reservation_code=None,
            payload=body,
            error_code="NON_2XX",
            error_message=response.text,
            http_status=response.status_code,
        )

    async def confirm_booking(self, reservation_code: str, details: dict[str, Any]) -> str:
        result = await self.book(reservation_code, f"compat-{reservation_code}", details)
        if result.status == "SUCCESS":
            return result.supplier_reservation_code or "SUCCESS"
        raise Exception(result.error_message or "HTTP booking failed")
