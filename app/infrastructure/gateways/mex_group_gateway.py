import logging
from typing import Any, Dict

import httpx

from app.infrastructure.circuit_breaker import async_supplier_breaker
from app.application.interfaces.supplier_gateway import SupplierBookingResult, SupplierGateway


class MexGroupGateway(SupplierGateway):
    """
    Gateway para Mex Group (Mex Rent a Car).
    Migrado desde MexGroupRepository.php.
    
    Reglas de migración:
    - NO Disponibilidad (datos deben venir en snapshot).
    - NO Cancelación.
    - Auth vía Token Bearer (api/brokers/login).
    - Protocolo REST JSON.
    """

    def __init__(
        self,
        endpoint: str,
        user: str,
        password: str,
        timeout_seconds: float = 30.0,
        retry_times: int = 2,
    ) -> None:
        self._endpoint = endpoint.rstrip("/") + "/"
        self._user = user
        self._password = password
        self._timeout = timeout_seconds
        self._retry_times = retry_times
        self._logger = logging.getLogger(__name__)
        # Token cache simple en memoria de la instancia
        self._token = None

    async def _get_token(self) -> str:
        """
        Obtiene token de autenticación.
        Mapea: MexGroupRepository::login / getToken
        Nota: Implementación simplificada sin cache persistente distribuido por ahora.
        """
        if self._token:
            return self._token

        url = f"{self._endpoint}api/brokers/login"
        payload = {"user": self._user, "password": self._password}
        
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                
                if data.get("type") == "success":
                    self._token = data.get("data", {}).get("token")
                    return self._token
                else:
                    raise Exception(f"Login failed: {data.get('message')}")
        except Exception as e:
            self._logger.error(f"MexGroup Auth failed: {str(e)}")
            raise

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
                error_message="Snapshot required for MexGroup booking",
            )
        
        if not self._endpoint:
             return SupplierBookingResult(
                status="FAILED",
                error_code="NO_ENDPOINT",
                error_message="MexGroup endpoint not configured",
            )

        # 1. Preparar Datos
        supplier_data = reservation_snapshot.get("supplier_specific_data") or {}
        
        rate_code = supplier_data.get("rate_code") or reservation_snapshot.get("rate_code")
        class_code = supplier_data.get("class_code") or supplier_data.get("class") or reservation_snapshot.get("class")
        rate_id = supplier_data.get("rate_id") or supplier_data.get("id_rate") or reservation_snapshot.get("rate_id")
        
        if not rate_code or not class_code or not rate_id:
             return SupplierBookingResult(
                status="FAILED",
                error_code="MISSING_SUPPLIER_DATA",
                error_message="Missing rate_code, class, or rate_id in snapshot",
            )

        # Fechas ISO con T
        pu_date = reservation_snapshot.get("pickup_datetime")
        if not pu_date:
            d = reservation_snapshot.get("pickup_date")
            t = reservation_snapshot.get("pickup_time", "12:00")
            pu_date = f"{d}T{t}:00"
        
        do_date = reservation_snapshot.get("dropoff_datetime")
        if not do_date:
            d = reservation_snapshot.get("dropoff_date")
            t = reservation_snapshot.get("dropoff_time", "12:00")
            do_date = f"{d}T{t}:00"

        # Customer
        customer = reservation_snapshot.get("customer", {})
        first_name = customer.get("first_name") or "Driver"
        last_name = customer.get("last_name") or "Name"
        
        # Flight info (opcional)
        airline = reservation_snapshot.get("airline") or ""
        flight = reservation_snapshot.get("flight") or ""
        
        # Payload
        payload = {
            "pickup_location": reservation_snapshot.get("pickup_location_code", "MEX"),
            "dropoff_location": reservation_snapshot.get("dropoff_location_code", "MEX"),
            "pickup_date": pu_date,
            "dropoff_date": do_date,
            "rate_code": str(rate_code),
            "class": str(class_code),
            "id_rate": str(rate_id),
            "email": "noreply@mexicocarrental.com.mx", # Legacy value
            "first_name": first_name,
            "last_name": last_name,
            "airline": airline,
            "flight": flight,
            "chain_code": "MX",
            "extras": [] # Extras logic simplified/omitted per rule (focus on core booking)
        }
        
        # Corporate setup logic (legacy check reservation status 'dpa')
        # Here we check if it's in supplier data
        if supplier_data.get("corporate_setup"):
            payload["corporate_setup"] = supplier_data["corporate_setup"]

        # 2. Obtener Token
        try:
            token = await self._get_token()
        except Exception as e:
            return SupplierBookingResult(status="FAILED", error_code="AUTH_ERROR", error_message=str(e))

        # 3. Enviar Request
        url = f"{self._endpoint}api/brokers/booking-engine/reserve"
        headers = {
            "Authorization": f"Bearer {token}",
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
                        # retry logic managed by loop
                
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

        # 4. Parsear Respuesta
        try:
            json_resp = response.json()
            data = json_resp.get("data", {})
            conf_id = data.get("noConfirmation")
            
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
        
        raise Exception(f"MexGroup booking failed: {result.error_message or result.error_code}")
