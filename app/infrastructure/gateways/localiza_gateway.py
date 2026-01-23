import logging
import xml.etree.ElementTree as ET
from typing import Any, Dict

import httpx

from app.application.interfaces.supplier_gateway import SupplierBookingResult, SupplierGateway
from app.infrastructure.circuit_breaker import async_supplier_breaker


class LocalizaGateway(SupplierGateway):
    """
    Gateway para Localiza.
    Migrado desde LocalizaRepository.php (parcialmente, ya que legacy solo tenía Availability).
    
    Implementación de Reserva (Book):
    - Inferida del estándar OTA (OTA_VehResRQ) y patrones de Auth de Availability.
    - Auth: HTTP Basic Auth + EchoToken + RequestorID (Type 5).
    - Protocolo: SOAP 1.1 Envelope.
    """

    def __init__(
        self,
        endpoint: str,
        username: str,
        password: str,
        echo_token: str,
        requestor_id: str,
        timeout_seconds: float = 30.0,
        retry_times: int = 2,
    ) -> None:
        self._endpoint = endpoint
        self._username = username
        self._password = password
        self._echo_token = echo_token
        self._requestor_id = requestor_id
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
                error_message="Snapshot required for Localiza booking",
            )

        if not self._endpoint:
             return SupplierBookingResult(
                status="FAILED",
                error_code="NO_ENDPOINT",
                error_message="Localiza endpoint not configured",
            )

        # 1. Preparar Datos
        supplier_data = reservation_snapshot.get("supplier_specific_data") or {}
        # Necesitamos size/category o SIZ/VEC
        veh_size = supplier_data.get("veh_size") or supplier_data.get("size")
        veh_category = supplier_data.get("veh_category") or supplier_data.get("category")
        
        # Fechas ISO format (YYYY-MM-DDTHH:MM:SS)
        pu_date = reservation_snapshot.get("pickup_datetime") or f"{reservation_snapshot.get('pickup_date')}T{reservation_snapshot.get('pickup_time', '00:00')}:00"
        do_date = reservation_snapshot.get("dropoff_datetime") or f"{reservation_snapshot.get('dropoff_date')}T{reservation_snapshot.get('dropoff_time', '00:00')}:00"
        
        pu_loc = reservation_snapshot.get("pickup_location_code") or "GRU"
        do_loc = reservation_snapshot.get("dropoff_location_code") or pu_loc

        # Customer
        customer = reservation_snapshot.get("customer", {})
        first_name = customer.get("first_name") or "Driver"
        last_name = customer.get("last_name") or "Name"
        email = customer.get("email") or "reservaciones@mexicocarrental.com.mx"

        # 2. Construir XML Payload (OTA_VehResRQ dentro de SOAP)
        # Namespace OTA 2003/05 según legacy
        
        veh_pref_xml = ""
        if veh_size or veh_category:
            size_attr = f' Size="{veh_size}"' if veh_size else ""
            cat_attr = f' VehicleCategory="{veh_category}"' if veh_category else ""
            veh_pref_xml = f"""<VehPref>
                    <VehClass{size_attr}/>
                    <VehType{cat_attr}/>
                </VehPref>"""

        xml_body = f"""<OTA_VehResRQ EchoToken="{self._echo_token}" Version="2.001" xmlns="http://www.opentravel.org/OTA/2003/05">
            <POS>
                <Source>
                    <RequestorID Type="5" ID="{self._requestor_id}"/>
                </Source>
            </POS>
            <VehResRQCore>
                <VehRentalCore PickUpDateTime="{pu_date}" ReturnDateTime="{do_date}">
                    <PickUpLocation LocationCode="{pu_loc}"/>
                    <ReturnLocation LocationCode="{do_loc}"/>
                </VehRentalCore>
                {veh_pref_xml}
                <Customer>
                    <Primary>
                        <PersonName>
                            <GivenName>{first_name}</GivenName>
                            <Surname>{last_name}</Surname>
                        </PersonName>
                        <Email>{email}</Email>
                    </Primary>
                </Customer>
            </VehResRQCore>
        </OTA_VehResRQ>"""

        envelope = f"""<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ota="http://www.opentravel.org/OTA/2003/05">
    <soapenv:Header/>
    <soapenv:Body>
        {xml_body}
    </soapenv:Body>
</soapenv:Envelope>"""

        # 3. Enviar Request
        headers = {
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': 'OTA_VehResRQ' # Inferido, legacy usaba OTA_VehAvailRateRQ
        }
        
        auth = (self._username, self._password)

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = None
                for attempt in range(self._retry_times + 1):
                    try:
                        response = await client.post(self._endpoint, content=envelope, headers=headers, auth=auth)
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

        # 4. Parsear Respuesta (OTA_VehResRS)
        try:
            # Eliminar namespaces para facilitar parseo
            # O usar lógica robusta con namespaces
            content = response.text
            root = ET.fromstring(content)
            
            # Buscar Body -> OTA_VehResRS
            # Debido a variaciones de prefijos, buscamos OTA_VehResRS donde sea
            res_rs = None
            for elem in root.iter():
                if "OTA_VehResRS" in elem.tag:
                    res_rs = elem
                    break
            
            if res_rs is None:
                return SupplierBookingResult(status="FAILED", error_code="INVALID_SOAP", payload={"response": content})

            # Check Success/Errors
            # OTA standard: <Success/> element present means success
            is_success = False
            for child in res_rs:
                if "Success" in child.tag:
                    is_success = True
                    break
            
            if not is_success:
                # Buscar errores
                errors_node = None
                for child in res_rs:
                    if "Errors" in child.tag:
                        errors_node = child
                        break
                
                msg = "Unknown Error"
                if errors_node is not None:
                     for err in errors_node:
                         msg = err.get("ShortText") or err.text or msg
                
                return SupplierBookingResult(status="FAILED", error_code="SUPPLIER_ERROR", error_message=msg)

            # Extraer ConfID
            # Path: VehResRSCore/VehReservation/VehSegmentCore/ConfID
            conf_id = None
            
            # Helper recursivo simple para buscar ConfID ignorando NS
            def find_conf_id(element):
                for child in element:
                    if "ConfID" in child.tag:
                        return child.get("ID")
                    res = find_conf_id(child)
                    if res: return res
                return None

            conf_id = find_conf_id(res_rs)
            
            if not conf_id:
                 # A veces Localiza devuelve confirmación en otro lado o status
                 return SupplierBookingResult(
                     status="FAILED", 
                     error_code="NO_CONFIRMATION_ID", 
                     payload={"response": content}
                )

            return SupplierBookingResult(
                status="SUCCESS",
                supplier_reservation_code=conf_id,
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
        
        raise Exception(f"Localiza booking failed: {result.error_message or result.error_code}")
