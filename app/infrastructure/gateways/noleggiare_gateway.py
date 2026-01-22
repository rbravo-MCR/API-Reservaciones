import logging
import xml.etree.ElementTree as ET
import uuid
from typing import Any, Dict

import httpx

from app.infrastructure.circuit_breaker import async_supplier_breaker
from app.application.interfaces.supplier_gateway import SupplierBookingResult, SupplierGateway


class NoleggiareGateway(SupplierGateway):
    """
    Gateway para Noleggiare.
    Migrado desde NoleggiareRepository.php.
    
    Reglas de migración:
    - NO Disponibilidad.
    - NO Cancelación.
    - Auth vía OTA POS (RequestorID).
    - Protocolo SOAP 1.1 manual (OTA standard).
    """

    def __init__(
        self,
        endpoint: str,
        username: str,
        password: str,
        company: str,
        target: str = "Test",
        version: str = "1.0",
        timeout_seconds: float = 30.0,
        retry_times: int = 2,
    ) -> None:
        self._endpoint = endpoint
        self._username = username
        self._password = password
        self._company = company
        self._target = target
        self._version = version
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
                error_message="Snapshot required for Noleggiare booking",
            )
            
        # 1. Datos del Proveedor
        supplier_data = reservation_snapshot.get("supplier_specific_data") or {}
        sipp_code = supplier_data.get("sipp_code") or supplier_data.get("sippCode") or reservation_snapshot.get("acriss_code")
        
        if not sipp_code:
             return SupplierBookingResult(
                status="FAILED",
                error_code="MISSING_SUPPLIER_DATA",
                error_message="Missing 'sipp_code' (ACRISS) in snapshot",
            )
            
        # 2. Fechas (ISO 8601 con Z)
        def to_iso_z(d, t):
            if not d: return ""
            t = t or "09:00:00"
            if len(t) == 5: t += ":00"
            return f"{d}T{t}Z"

        pu_date = to_iso_z(reservation_snapshot.get("pickup_date"), reservation_snapshot.get("pickup_time"))
        do_date = to_iso_z(reservation_snapshot.get("dropoff_date"), reservation_snapshot.get("dropoff_time"))
        
        # 3. Locations
        pu_loc = reservation_snapshot.get("pickup_location_code") or "FCO"
        do_loc = reservation_snapshot.get("dropoff_location_code") or "FCO"

        # 4. Customer
        customer = reservation_snapshot.get("customer", {})
        first_name = customer.get("first_name") or "Driver"
        last_name = customer.get("last_name") or "Name"
        email = customer.get("email") or "reservaciones@mexicocarrental.com.mx"
        phone = customer.get("phone") or "000000000"

        # 5. Flight (Opcional)
        flight_no = reservation_snapshot.get("flight") or ""
        
        # 6. Construir XML OTA
        echo_token = str(uuid.uuid4())
        ns_ota = "http://www.opentravel.org/OTA/2003/05"
        
        # POS Block
        pos = f"""<ns:POS>
          <ns:Source>
            <ns:RequestorID ID="{self._username}" MessagePassword="{self._password}">
                <ns:CompanyName>{self._company}</ns:CompanyName>
            </ns:RequestorID>
          </ns:Source>
        </ns:POS>"""
        
        # Info Block
        arrival_details = ""
        if flight_no:
            arrival_details = f'<ns:ArrivalDetails Number="{flight_no}" ArrivalDateTime="{pu_date}"/>'
            
        payment_info = ""
        # Legacy sends payment info only if amount is present, hardcoded to bonifico charge
        # We omit amount logic for now unless critical, or send generic payment pref
        
        xml_body = f"""<ns:OTA_VehResRQ Version="{self._version}" Target="{self._target}" TimeStamp="{pu_date}" EchoToken="{echo_token}" xmlns:ns="{ns_ota}">
            {pos}
            <ns:VehResRQCore>
                <ns:VehRentalCore PickUpDateTime="{pu_date}" ReturnDateTime="{do_date}">
                  <ns:PickUpLocation LocationCode="{pu_loc}"/>
                  <ns:ReturnLocation LocationCode="{do_loc}"/>
                </ns:VehRentalCore>
                <ns:Customer>
                  <ns:Primary>
                    <ns:PersonName>
                      <ns:GivenName>{first_name}</ns:GivenName>
                      <ns:Surname>{last_name}</ns:Surname>
                    </ns:PersonName>
                    <ns:Telephone PhoneTechType="1" PhoneNumber="{phone}"/>
                    <ns:Email>{email}</ns:Email>
                  </ns:Primary>
                </ns:Customer>
                <ns:VehPref Code="{sipp_code}" />
            </ns:VehResRQCore>
            <ns:VehResRQInfo>
                {arrival_details}
            </ns:VehResRQInfo>
        </ns:OTA_VehResRQ>"""

        envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ns="{ns_ota}">
  <soapenv:Header/>
  <soapenv:Body>
    {xml_body}
  </soapenv:Body>
</soapenv:Envelope>"""

        # 7. Enviar
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": "OTA_VehResRQ",
            "Accept-Encoding": "identity"
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = None
                for attempt in range(self._retry_times + 1):
                    try:
                        response = await client.post(self._endpoint, content=envelope, headers=headers)
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

        # 8. Parsear
        try:
            content = response.text
            # Sanitize minimal (legacy did complex sanitization)
            if content.strip().startswith("<?xml"):
                content = content[content.find("?>")+2:]
            
            root = ET.fromstring(content)
            
            # Find OTA_VehResRS (ignoring NS logic for simplicity or using wildcard)
            res_rs = None
            for elem in root.iter():
                if "OTA_VehResRS" in elem.tag:
                    res_rs = elem
                    break
            
            if res_rs is None:
                 return SupplierBookingResult(status="FAILED", error_code="INVALID_SOAP", payload={"response": content})

            # Check Errors
            errors = []
            for elem in res_rs.iter():
                if "Errors" in elem.tag:
                    for err in elem:
                        if "Error" in err.tag:
                            errors.append(err.get("ShortText") or err.text or "Unknown OTA Error")
            
            if errors:
                return SupplierBookingResult(
                    status="FAILED",
                    error_code="SUPPLIER_ERROR",
                    error_message="; ".join(errors),
                    payload={"response": content}
                )
            
            # Find ConfID
            conf_id = None
            for elem in res_rs.iter():
                if "ConfID" in elem.tag:
                    conf_id = elem.get("ID")
                    if conf_id: break
            
            if not conf_id:
                return SupplierBookingResult(
                    status="FAILED", 
                    error_code="NO_CONFIRMATION_ID", 
                    payload={"response": content}
                )

            return SupplierBookingResult(
                status="SUCCESS",
                supplier_reservation_code=str(conf_id),
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
        
        raise Exception(f"Noleggiare booking failed: {result.error_message or result.error_code}")
