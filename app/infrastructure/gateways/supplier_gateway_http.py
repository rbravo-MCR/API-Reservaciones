import json
import logging
from typing import Any

import httpx

from app.application.interfaces.supplier_gateway import SupplierBookingResult, SupplierGateway
from app.infrastructure.circuit_breaker import CircuitBreakerError, supplier_breaker

logger = logging.getLogger(__name__)


class SupplierGatewayHTTP(SupplierGateway):
    def __init__(self, base_url: str, timeout_seconds: float = 10.0) -> None:
        """
        HTTP-based supplier gateway with configurable timeout.

        Args:
            base_url: Base URL of the supplier API
            timeout_seconds: Request timeout in seconds (default: 10.0 for production safety)
        """
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def book(
        self, reservation_code: str, idem_key: str, reservation_snapshot=None
    ) -> SupplierBookingResult:
        """
        Book reservation with supplier API, protected by Circuit Breaker.

        The circuit breaker prevents cascading failures by failing fast when
        the supplier service is down or experiencing issues.

        Returns:
            SupplierBookingResult with status SUCCESS or FAILED
        """
        url = f"{self._base_url}/book"
        headers = {"Idempotency-Key": idem_key}
        payload: dict[str, Any] = {"reservation_code": reservation_code, "idem_key": idem_key}

        # Define the HTTP call as a callable for the circuit breaker
        async def _make_request():
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                return await client.post(url, json=payload, headers=headers)

        try:
            # Wrap the HTTP call with circuit breaker protection
            # Note: pybreaker doesn't natively support async, so we use call_async
            response = await supplier_breaker.call_async(_make_request)
        except CircuitBreakerError as exc:
            logger.error(
                "Supplier circuit breaker is open - service unavailable",
                extra={
                    "reservation_code": reservation_code,
                    "circuit_state": str(exc)
                }
            )
            return SupplierBookingResult(
                status="FAILED",
                supplier_reservation_code=None,
                payload=None,
                error_code="CIRCUIT_OPEN",
                error_message="Supplier service temporarily unavailable (circuit breaker open)",
                http_status=None,
            )
        except httpx.TimeoutException as exc:  # pragma: no cover - real gateway path
            logger.warning(
                "Supplier request timeout",
                extra={"reservation_code": reservation_code, "timeout": self._timeout}
            )
            return SupplierBookingResult(
                status="FAILED",
                supplier_reservation_code=None,
                payload=None,
                error_code="TIMEOUT",
                error_message=str(exc),
                http_status=None,
            )
        except httpx.HTTPError as exc:  # pragma: no cover - real gateway path
            logger.error(
                "Supplier HTTP error",
                exc_info=exc,
                extra={"reservation_code": reservation_code}
            )
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
