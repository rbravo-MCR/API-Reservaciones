import logging
from datetime import datetime
from typing import Any, Dict

import httpx

from app.application.interfaces.supplier_gateway import SupplierBookingResult, SupplierGateway
from app.infrastructure.circuit_breaker import async_supplier_breaker


class HertzArgentinaGateway(SupplierGateway):
    """
    Gateway para Hertz Argentina.
    Migrado desde HertzArgentinaRepository.php.
    
    Reglas de migración:
    - NO Disponibilidad.
    - NO Cancelación.
    - Auth interna (Token) requerida para confirmar reserva.
    - Paridad estricta en payload de confirmación.
    """

    def __init__(
        self,
        base_url: str,
        auth_url: str,
        username: str,
        password: str,
        client_id: str,
        grant_type: str,
        timeout_seconds: float = 30.0,
        retry_times: int = 2,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth_url = auth_url
        self._username = username
        self._password = password
        self._client_id = client_id
        self._grant_type = grant_type
        self._timeout = timeout_seconds
        self._retry_times = retry_times
        self._logger = logging.getLogger(__name__)

    async def _get_token(self) -> str:
        """
        Obtiene el token Bearer para autenticación.
        Mapea: HertzArgentinaRepository::getToken
        """
        payload = {
            "username": self._username,
            "password": self._password,
            "grant_type": self._grant_type,
            "client_id": self._client_id,
        }
        
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self._auth_url, data=payload)
                response.raise_for_status()
                data = response.json()
                return str(data.get("access_token", ""))
        except Exception as e:
            self._logger.error(f"HertzAR Auth failed: {str(e)}")
            raise

    def _calculate_age(self, birth_date_str: str) -> int:
        """
        Calcula edad desde string 'YYYY-MM-DD'.
        Mapea: HertzArgentinaRepository::calculateAge
        """
        if not birth_date_str:
            return 30 # Fallback seguro si no hay fecha
        try:
            birth_date = datetime.strptime(birth_date_str, "%Y-%m-%d")
            today = datetime.today()
            age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
            return age
        except ValueError:
            self._logger.warning(f"Invalid birth date format: {birth_date_str}")
            return 30 # Fallback por defecto

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
                error_message="Snapshot required for Hertz booking",
            )

        # Mapeo de datos del snapshot
        # Se asume que el snapshot contiene las llaves normalizadas del sistema
        customer_data = reservation_snapshot.get("customer", {})
        driver_data = reservation_snapshot.get("driver", {}) # A veces separado en driver
        
        # En PHP legacy $params recibía todo plano. Aquí intentamos extraer de estructura lógica
        # o usamos claves planas si vienen así en el snapshot legacy.
        
        first_name = customer_data.get("first_name") or driver_data.get("first_name") or reservation_snapshot.get("name") or "Driver"
        last_name = customer_data.get("last_name") or driver_data.get("last_name") or reservation_snapshot.get("lastname") or "Name"
        full_driver_name = f"{first_name} {last_name}"
        email = customer_data.get("email") or reservation_snapshot.get("driver_email") or "reservaciones@mexicocarrental.com.mx"
        
        dob = reservation_snapshot.get("birth_date") or reservation_snapshot.get("dob")
        age = self._calculate_age(str(dob)) if dob else 30
        
        license_nr = reservation_snapshot.get("license_number") or reservation_snapshot.get("license_nr") or "NA"
        license_exp = reservation_snapshot.get("license_expiration") or reservation_snapshot.get("license_exp") or "2030-01-01"
        license_country = reservation_snapshot.get("license_country") or reservation_snapshot.get("license_place") or "MX"

        # Datos de vehiculo y fechas
        model_code = reservation_snapshot.get("acriss_code") or reservation_snapshot.get("model")
        pu_date = reservation_snapshot.get("pickup_date") or reservation_snapshot.get("pu_date")
        do_date = reservation_snapshot.get("dropoff_date") or reservation_snapshot.get("do_date")
        delivery_place = reservation_snapshot.get("pickup_location_code") or reservation_snapshot.get("deliveryPlace")

        if not model_code or not pu_date or not do_date:
             return SupplierBookingResult(
                status="FAILED",
                error_code="MISSING_DATA",
                error_message="Missing mandatory data: model, pickup_date or dropoff_date",
            )

        # 1. Obtener Token
        try:
            token = await self._get_token()
        except Exception as e:
             return SupplierBookingResult(
                status="FAILED",
                error_code="AUTH_ERROR",
                error_message=f"Could not authenticate with Hertz: {str(e)}",
            )

        # 2. Construir Payload
        request_body = {
            "customer": {
                "firstName": first_name,
                "lastName": last_name,
                "name": full_driver_name, # PHP Legacy usaba params['driver_name'] que solía ser nombre completo
                "emailAddress": email,
                "age": age,
                "driverLicenceNumber": license_nr,
                "driverLicenseExpiration": license_exp,
                "driverLicenceCountry": license_country, 
            },
            "model": model_code,
            "fromDate": pu_date,
            "toDate": do_date,
            "deliveryPlace": delivery_place
        }

        # 3. Enviar Request
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
        
        url = f"{self._base_url}/Booking"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                # Retries simples
                response = None
                last_exception = None
                for attempt in range(self._retry_times + 1):
                    try:
                        response = await client.post(url, json=request_body, headers=headers)
                        if response.status_code < 500: # Break on non-server errors
                            break
                    except httpx.RequestError as exc:
                        last_exception = exc
                        if attempt == self._retry_times:
                            pass # Raise after loop or handle
                
                if last_exception and not response:
                     raise last_exception

        except httpx.RequestError as exc:
            return SupplierBookingResult(
                status="FAILED",
                error_code="NETWORK_ERROR",
                error_message=str(exc),
            )

        if not response:
             return SupplierBookingResult(status="FAILED", error_code="NO_RESPONSE")

        if not response.is_success:
             return SupplierBookingResult(
                status="FAILED",
                error_code="HTTP_ERROR",
                http_status=response.status_code,
                payload={"raw_response": response.text, "request": request_body},
            )

        # 4. Procesar Respuesta
        # PHP: if (isset($json)) return success
        try:
            resp_json = response.json()
        except Exception:
             return SupplierBookingResult(
                status="FAILED",
                error_code="INVALID_JSON",
                payload={"raw_response": response.text},
            )

        # Extraer ID de reserva si es posible. El PHP legacy no extraía un ID específico, 
        # solo devolvía el JSON completo.
        # Asumiremos que si es 200 OK y hay JSON, es éxito.
        # Intentamos buscar algún ID común en la respuesta para el log.
        booking_id = resp_json.get("id") or resp_json.get("bookingId") or resp_json.get("reservationNumber") or "CONFIRMED"

        return SupplierBookingResult(
            status="SUCCESS",
            supplier_reservation_code=str(booking_id),
            payload={"response": resp_json},
            http_status=response.status_code,
        )

    async def confirm_booking(self, reservation_code: str, details: Dict[str, Any]) -> str:
        """
        Wrapper de compatibilidad.
        """
        result = await self.book(
            reservation_code=reservation_code,
            idem_key=f"compat-{reservation_code}",
            reservation_snapshot=details
        )
        if result.status == "SUCCESS" and result.supplier_reservation_code:
            return result.supplier_reservation_code
        
        raise Exception(f"Hertz Argentina booking failed: {result.error_message or result.error_code}")
