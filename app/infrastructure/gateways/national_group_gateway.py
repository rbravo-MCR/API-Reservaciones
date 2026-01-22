import logging
from typing import Any, Dict

import httpx

from app.infrastructure.circuit_breaker import async_supplier_breaker
from app.application.interfaces.supplier_gateway import SupplierBookingResult, SupplierGateway


class NationalGroupGateway(SupplierGateway):
    """
    Gateway para National Group.
    Migrado desde NationalGroupRepository.php.
    
    Reglas de migración:
    - NO Disponibilidad.
    - NO Cancelación.
    - Auth vía Token estático (Bearer).
    - Protocolo REST JSON.
    """

    def __init__(
        self,
        endpoint: str,
        token: str,
        timeout_seconds: float = 30.0,
        retry_times: int = 2,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._token = token
        self._timeout = timeout_seconds
        self._retry_times = retry_times
        self._logger = logging.getLogger(__name__)

    @async_supplier_breaker
    async def book(
        self,
        reservation_code: str,
        idem_key: str,
        reservation_snapshot: dict[str, Any] | None = None,
    ) -> SupplierBookingResult:
        if not reservation_snapshot:
            return SupplierBookingResult(
                status="FAILED",
                error_code="MISSING_SNAPSHOT",
                error_message="Snapshot required for National booking",
            )

        if not self._endpoint:
             return SupplierBookingResult(
                status="FAILED",
                error_code="NO_ENDPOINT",
                error_message="National endpoint not configured",
            )

        # 1. Preparar Datos
        customer = reservation_snapshot.get("customer", {})
        first_name = customer.get("first_name") or "Driver"
        last_name = customer.get("last_name") or "Name"
        
        # Fechas ISO con T
        pu_date = reservation_snapshot.get("pickup_datetime")
        if not pu_date:
            d = reservation_snapshot.get("pickup_date")
            t = reservation_snapshot.get("pickup_time", "12:00:00")
            pu_date = f"{d}T{t}"
            
        do_date = reservation_snapshot.get("dropoff_datetime")
        if not do_date:
            d = reservation_snapshot.get("dropoff_date")
            t = reservation_snapshot.get("dropoff_time", "12:00:00")
            do_date = f"{d}T{t}"

        # Datos adicionales legacy
        supplier_data = reservation_snapshot.get("supplier_specific_data") or {}
        season_id = supplier_data.get("season_id") or 1
        net_rate = reservation_snapshot.get("net_rate") or 0.0
        acriss = reservation_snapshot.get("acriss_code") or reservation_snapshot.get("acriss") or "ECAR"
        category = reservation_snapshot.get("category_name") or "Economy"
        dest_code = reservation_snapshot.get("destination_code") or "CUN"

        payload = {
            "season_id": season_id,
            "destination_code": dest_code,
            "office_pickup": reservation_snapshot.get("pickup_location_code"),
            "office_dropoff": reservation_snapshot.get("dropoff_location_code"),
            "pickup_date": pu_date,
            "dropoff_date": do_date,
            "net_rate": net_rate,
            "sipp_code": acriss,
            "group": category,
            "name": first_name,
            "last_name": last_name,
            "email": "reservaciones@mexicocarrental.com.mx", # Legacy hardcoded
            "phone": "5541637157", # Legacy hardcoded
            "age": 0, # Legacy hardcoded
            "status": "N" # New
        }

        # 2. Enviar Request
        url = f"{self._endpoint}/otas/reservaciones"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = None
                for attempt in range(self._retry_times + 1):
                    try:
                        response = await client.post(url, json=payload, headers=headers)
                        if response.status_code < 500:
                            break
                    except httpx.RequestError:
                        if attempt == self._retry_times:
                            raise
                
                if not response:
                     raise httpx.RequestError("No response received")

        except httpx.RequestError as exc:
            return SupplierBookingResult(status="FAILED", error_code="NETWORK_ERROR", error_message=str(exc))

        if not response.is_success:
             return SupplierBookingResult(
                status="FAILED",
                error_code="HTTP_ERROR",
                http_status=response.status_code,
                payload={"raw_response": response.text},
            )

        # 3. Parsear Respuesta
        try:
            json_resp = response.json()
            # Legacy: data.id
            conf_id = json_resp.get("data", {}).get("id")
            
            if not conf_id:
                return SupplierBookingResult(
                    status="FAILED", 
                    error_code="NO_CONFIRMATION_ID", 
                    payload={"response": json_resp}
                )

            return SupplierBookingResult(
                status="SUCCESS",
                supplier_reservation_code=str(conf_id),
                payload={"response": json_resp},
                http_status=response.status_code
            )

        except Exception as e:
            return SupplierBookingResult(status="FAILED", error_code="PROCESSING_ERROR", error_message=str(e))

    async def confirm_booking(self, reservation_code: str, details: Dict[str, Any]) -> str:
        result = await self.book(
            reservation_code=reservation_code,
            idem_key=f"compat-{reservation_code}",
            reservation_snapshot=details
        )
        if result.status == "SUCCESS" and result.supplier_reservation_code:
            return result.supplier_reservation_code
        
        raise Exception(f"National booking failed: {result.error_message or result.error_code}")
