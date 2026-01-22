import logging
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Dict

import httpx

from app.infrastructure.circuit_breaker import async_supplier_breaker
from app.application.interfaces.supplier_gateway import SupplierBookingResult, SupplierGateway


class InfinityGroupGateway(SupplierGateway):
    """
    Gateway para Infinity Group (Infinity Car Rental).
    Migrado desde InfinityGroupRepository.php.
    
    Reglas de migración:
    - NO Disponibilidad.
    - NO Cancelación.
    - Auth vía RequestorID en el XML (sin token previo).
    - Comunicación vía GET con parámetro XML.
    """

    def __init__(
        self,
        endpoint: str,
        requestor_id: str = "92",
        timeout_seconds: float = 30.0,
        retry_times: int = 2,
    ) -> None:
        self._endpoint = endpoint
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
                error_message="Snapshot required for Infinity booking",
            )
        
        if not self._endpoint:
             return SupplierBookingResult(
                status="FAILED",
                error_code="NO_ENDPOINT",
                error_message="Infinity endpoint not configured",
            )

        # 1. Extraer datos necesarios
        # Legacy: usaba 'quotation' para sacar car_type y vendor_rate_id
        # Asumimos que estos datos se guardaron en 'supplier_specific_data' en el snapshot
        supplier_data = reservation_snapshot.get("supplier_specific_data") or {}
        
        # Fallback a claves planas si vienen en el snapshot raíz (compatibilidad)
        car_type = supplier_data.get("car_type") or reservation_snapshot.get("car_type")
        vendor_rate_id = supplier_data.get("vendor_rate_id") or reservation_snapshot.get("vendor_rate_id")
        
        if not car_type or not vendor_rate_id:
             return SupplierBookingResult(
                status="FAILED",
                error_code="MISSING_SUPPLIER_DATA",
                error_message="Missing 'car_type' or 'vendor_rate_id' in snapshot",
            )

        # Datos Generales
        # Fechas deben incluir hora (YYYY-MM-DDTHH:MM:SS) o (YYYY-MM-DD HH:MM)
        # El legacy hacía sprintf('%sT%s', date, time)
        pu_date = reservation_snapshot.get("pickup_date") or reservation_snapshot.get("pu_date")
        pu_time = reservation_snapshot.get("pickup_time") or "09:00"
        do_date = reservation_snapshot.get("dropoff_date") or reservation_snapshot.get("do_date")
        do_time = reservation_snapshot.get("dropoff_time") or "09:00"
        
        # Normalizar formato fecha/hora ISO 8601 simple
        # Si pu_date ya tiene T, lo usamos, si no combinamos
        if "T" not in str(pu_date):
            pu_datetime = f"{pu_date}T{pu_time}"
        else:
            pu_datetime = str(pu_date)

        if "T" not in str(do_date):
            do_datetime = f"{do_date}T{do_time}"
        else:
            do_datetime = str(do_date)

        # Locations
        pu_loc_code = reservation_snapshot.get("pickup_location_code") or "CUN"
        do_loc_code = reservation_snapshot.get("dropoff_location_code") or "CUN"

        # Cliente
        customer = reservation_snapshot.get("customer", {})
        first_name = customer.get("first_name") or reservation_snapshot.get("name") or "Driver"
        last_name = customer.get("last_name") or reservation_snapshot.get("lastname") or "Name"
        # Legacy hardcodea el email
        email = "reservaciones@mexicocarrental.com.mx"
        
        # Referencia
        ref_id = reservation_snapshot.get("token_id") or reservation_code

        # 2. Construir XML
        # Usamos f-string para replicar la estructura exacta del legacy
        # Nota: Legacy 'OTA_VehResRQ' con 'Version="1.00"'
        xml_payload = f"""<?xml version="1.0"?>
<OTA_VehResRQ Version="1.00">
    <POS>
        <Source>
            <RequestorID ID="{self._requestor_id}"/>
        </Source>
    </POS>
    <BookingReferenceID>
        <UniqueID_Type ID="{ref_id}"/>
    </BookingReferenceID>
    <VehResRQCore>
        <VehRentalCore PickUpDateTime="{pu_datetime}" ReturnDateTime="{do_datetime}">
            <PickUpLocation LocationCode="{pu_loc_code}"/>
            <ReturnLocation LocationCode="{do_loc_code}"/>
        </VehRentalCore>
        <VehPref VendorCarType="{car_type}">
            <VehClass>{car_type}</VehClass>
            <VehType/>
        </VehPref>
        <RateQualifier VendorRateID="{vendor_rate_id}"/>
        <Customer>
            <Primary>
                <PersonName>
                    <GivenName>{first_name}</GivenName>
                    <Surname>{last_name}</Surname>
                </PersonName>
                <Email>
                    <Value>{email}</Value>
                </Email>
            </Primary>
        </Customer>
    </VehResRQCore>
</OTA_VehResRQ>"""

        # 3. Enviar Request (GET ?XML=...)
        encoded_xml = urllib.parse.quote(xml_payload)
        url = f"{self._endpoint}?XML={encoded_xml}"
        
        headers = {'Accept': 'application/xml'}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = None
                for attempt in range(self._retry_times + 1):
                    try:
                        response = await client.get(url, headers=headers)
                        # Break si es success o error del cliente (4xx), retry si es server error (5xx)
                        if response.status_code < 500:
                            break
                    except httpx.RequestError:
                         if attempt == self._retry_times:
                            raise
                
                if not response:
                     raise httpx.RequestError("No response received")

        except httpx.RequestError as exc:
             return SupplierBookingResult(
                status="FAILED",
                error_code="NETWORK_ERROR",
                error_message=str(exc),
            )

        if not response.is_success:
             return SupplierBookingResult(
                status="FAILED",
                error_code="HTTP_ERROR",
                http_status=response.status_code,
                payload={"raw_response": response.text},
            )

        # 4. Parsear Respuesta XML
        try:
            # Limpiar response (legacy hace ltrim si empieza con <)
            content = response.text.strip()
            # A veces viene con BOM o espacios
            if not content.startswith("<"):
                # Intentar buscar donde empieza
                start = content.find("<")
                if start != -1:
                    content = content[start:]
            
            root = ET.fromstring(content)
            
            # Buscar ConfID
            # Path: VehResRSCore -> VehReservation -> VehSegmentCore -> ConfID -> @ID
            # Namespaces suelen ser un dolor en OTA, el legacy no parecia usar namespaces estrictos
            # pero ET.fromstring los parsea si existen.
            # Haremos una busqueda agnostica o directa.
            
            # Intentar buscar namespace si existe
            ns = {}
            if 'xmlns' in content:
                 # simple hack, if needed. For now assume no NS or ignore it via find
                 pass

            # Navegacion manual segura
            conf_id = None
            veh_res_core = root.find("VehResRSCore")
            if veh_res_core is not None:
                veh_reservation = veh_res_core.find("VehReservation")
                if veh_reservation is not None:
                    veh_seg_core = veh_reservation.find("VehSegmentCore")
                    if veh_seg_core is not None:
                        conf_node = veh_seg_core.find("ConfID")
                        if conf_node is not None:
                            conf_id = conf_node.get("ID")
            
            # Verificar errores si no hay ID
            if not conf_id:
                errors = root.find("Errors")
                error_msg = "Unknown error"
                if errors is not None:
                    err = errors.find("Error")
                    if err is not None:
                        error_msg = err.get("ShortText") or err.text or "Error node found"
                
                return SupplierBookingResult(
                    status="FAILED",
                    error_code="SUPPLIER_ERROR",
                    error_message=error_msg,
                    payload={"response": content}
                )

            return SupplierBookingResult(
                status="SUCCESS",
                supplier_reservation_code=conf_id,
                payload={"response": content},
                http_status=response.status_code
            )

        except ET.ParseError:
            return SupplierBookingResult(
                status="FAILED",
                error_code="INVALID_XML",
                payload={"raw_response": response.text},
            )
        except Exception as e:
            return SupplierBookingResult(
                status="FAILED",
                error_code="PROCESSING_ERROR",
                error_message=str(e),
            )

    async def confirm_booking(self, reservation_code: str, details: Dict[str, Any]) -> str:
        """Compatibility wrapper."""
        result = await self.book(
            reservation_code=reservation_code,
            idem_key=f"compat-{reservation_code}",
            reservation_snapshot=details
        )
        if result.status == "SUCCESS" and result.supplier_reservation_code:
            return result.supplier_reservation_code
        
        raise Exception(f"Infinity booking failed: {result.error_message or result.error_code}")
