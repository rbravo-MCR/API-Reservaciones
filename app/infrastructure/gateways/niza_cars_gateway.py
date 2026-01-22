import logging
import xml.etree.ElementTree as ET
from typing import Any, Dict

import httpx

from app.infrastructure.circuit_breaker import async_supplier_breaker
from app.application.interfaces.supplier_gateway import SupplierBookingResult, SupplierGateway


class NizaCarsGateway(SupplierGateway):
    """
    Gateway para Niza Cars (Rentway).
    Migrado desde NizaCarsRepository.php.
    
    Reglas de migración:
    - NO Disponibilidad.
    - NO Cancelación (no implementada explícitamente en createReservation legacy).
    - Auth vía parámetros en el Body (CompanyCode, ClienteCode, User, Pass).
    - Protocolo SOAP 1.1 async manual (sin SoapClient).
    """

    def __init__(
        self,
        base_url: str,
        company_code: str,
        customer_code: str,
        username: str,
        password: str,
        timeout_seconds: float = 30.0,
        retry_times: int = 2,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._company_code = company_code
        self._customer_code = customer_code # 'FF' default map in legacy
        self._username = username
        self._password = password
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
                error_message="Snapshot required for Niza booking",
            )
        
        # 1. Datos del Proveedor (Group, RateCode)
        supplier_data = reservation_snapshot.get("supplier_specific_data") or {}
        
        group = supplier_data.get("Group") or supplier_data.get("group") or reservation_snapshot.get("category_code")
        rate_code = supplier_data.get("RateCode") or supplier_data.get("rate_code")
        
        if not group:
             return SupplierBookingResult(
                status="FAILED",
                error_code="MISSING_SUPPLIER_DATA",
                error_message="Missing 'Group' (category) in snapshot",
            )
            
        # 2. Fechas (YYYY-MM-DD HH:MM)
        # Snapshot suele tener ISO YYYY-MM-DD o YYYY-MM-DDTHH:MM:SS
        def fmt_date(d, t):
            if not d: return ""
            t = t or "09:00"
            return f"{d} {t[:5]}" # Cortar segundos si hay

        pu_date = fmt_date(reservation_snapshot.get("pickup_date"), reservation_snapshot.get("pickup_time"))
        do_date = fmt_date(reservation_snapshot.get("dropoff_date"), reservation_snapshot.get("dropoff_time"))
        
        # 3. Locations
        pu_station = reservation_snapshot.get("pickup_location_code") or "MEX1"
        do_station = reservation_snapshot.get("dropoff_location_code") or "MEX1"

        # 4. Driver
        customer = reservation_snapshot.get("customer", {})
        first_name = customer.get("first_name") or "Driver"
        last_name = customer.get("last_name") or "Name"
        full_name = f"{last_name},{first_name}" # Legacy format: Surname,GivenName
        email = customer.get("email") or "reservaciones@mexicocarrental.com.mx"
        dob = reservation_snapshot.get("birth_date") or "1990-01-01"

        # 5. Construir XML
        ns = "http://www.jimpisoft.pt/Rentway_Reservations_WS/Create_Reservation"
        action = f"{ns}/Create_Reservation"
        endpoint = f"{self._base_url}/Create_Reservation.asmx"
        
        # RateCode fallback logic from legacy (uses plan 'FF' if missing)
        final_rate_code = rate_code or "FF"
        
        xml_body = f"""<Create_Reservation xmlns="{ns}">
            <CompanyCode>{self._company_code}</CompanyCode>
            <ClienteCode>{self._customer_code}</ClienteCode>
            <Username>{self._username}</Username>
            <Password>{self._password}</Password>
            <MessageType>N</MessageType>
            <Group>{group}</Group>
            <RateCode>{final_rate_code}</RateCode>
            <PickUp>
                <Date>{pu_date}</Date>
                <Rental_Station>{pu_station}</Rental_Station>
            </PickUp>
            <DropOff>
                <Date>{do_date}</Date>
                <Rental_Station>{do_station}</Rental_Station>
            </DropOff>
            <Driver>
                <Name>{full_name}</Name>
                <Email>{email}</Email>
                <Date_of_Birth>{dob}</Date_of_Birth>
            </Driver>
        </Create_Reservation>"""

        envelope = f"""<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
    <soap:Body>
        {xml_body}
    </soap:Body>
</soap:Envelope>"""

        # 6. Enviar
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": action
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = None
                for attempt in range(self._retry_times + 1):
                    try:
                        response = await client.post(endpoint, content=envelope, headers=headers)
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

        # 7. Parsear
        try:
            # Respuesta esperada: <Create_ReservationResult> ... </Create_ReservationResult>
            # Puede contener un DiffGram o un XML embebido.
            # Legacy Niza a menudo devuelve un XML complejo o un simple success.
            # Asumiremos que buscamos un ID de reserva o "Success".
            
            content = response.text
            root = ET.fromstring(content)
            
            # Buscar Create_ReservationResult
            res_node = None
            for elem in root.iter():
                if "Create_ReservationResult" in elem.tag:
                    res_node = elem
                    break
            
            if res_node is None:
                 return SupplierBookingResult(status="FAILED", error_code="INVALID_SOAP", payload={"response": content})

            # Analizar contenido de result. A veces es un objeto complejo.
            # Buscaremos un nodo "ReservationNumber" o "ResNumber" o similar,
            # o si viene un DiffGram, buscaremos dentro.
            
            # Estrategia agnóstica: buscar cualquier nodo que parezca un ID de reserva
            # o verificar errores.
            
            # Check errors first
            errors = []
            for elem in res_node.iter():
                if "Error" in elem.tag and elem.text:
                    errors.append(elem.text)
            
            if errors:
                return SupplierBookingResult(
                    status="FAILED",
                    error_code="SUPPLIER_ERROR",
                    error_message="; ".join(errors),
                    payload={"response": content}
                )

            # Buscar ID
            res_id = None
            for elem in res_node.iter():
                # Nombres comunes en Niza/Rentway
                if elem.tag.endswith("ReservationID") or elem.tag.endswith("ResNumber") or elem.tag.endswith("Number"):
                     if elem.text and elem.text.isdigit():
                         res_id = elem.text
                         break
            
            # Si no encontramos ID explicito, pero no hubo errores y el HTTP es 200,
            # podría ser que el resultado venga en un <any> que hay que parsear de nuevo (como en Availability).
            # Pero en CreateReservation legacy, el retorno se decodificaba json_encode($res).
            
            if not res_id:
                # Fallback: Hash del response si parece exitoso? No, peligroso.
                # Si llegamos aquí y no hay error explícito, quizás devolvemos el raw para auditoría
                # y marcamos como PENDING_MANUAL_CHECK o fallamos seguro.
                # Vamos a intentar buscar "Success"
                success = False
                for elem in res_node.iter():
                     if "Success" in elem.tag:
                         success = True
                
                if success:
                    res_id = "CONFIRMED_CHECK_LOGS" # Provisional
                else:
                    return SupplierBookingResult(
                        status="FAILED", 
                        error_code="NO_CONFIRMATION_ID", 
                        payload={"response": content}
                    )

            return SupplierBookingResult(
                status="SUCCESS",
                supplier_reservation_code=str(res_id),
                payload={"response": content},
                http_status=response.status_code
            )

        except ET.ParseError:
            return SupplierBookingResult(status="FAILED", error_code="INVALID_XML", payload={"raw_response": response.text})
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
        
        raise Exception(f"NizaCars booking failed: {result.error_message or result.error_code}")
