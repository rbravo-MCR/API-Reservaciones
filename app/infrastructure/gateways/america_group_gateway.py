import logging
from typing import Any
from xml.etree.ElementTree import Element, SubElement, fromstring, tostring

import httpx

from app.application.interfaces.supplier_gateway import SupplierBookingResult, SupplierGateway


class AmericaGroupGateway(SupplierGateway):
    """
    Gateway específico para America Car Rental (America Group).
    Envía OTA_VehResRQ por HTTP GET ?XML=... y espera ConfID en la respuesta.
    """

    def __init__(
        self,
        endpoint: str,
        requestor_id: str,
        timeout_seconds: float = 5.0,
        retry_times: int = 2,
        retry_sleep_ms: int = 300,
    ) -> None:
        self._endpoint = endpoint.rstrip("?")
        self._requestor_id = requestor_id
        self._timeout = timeout_seconds
        self._retry_times = retry_times
        self._retry_sleep_ms = retry_sleep_ms
        self._logger = logging.getLogger(__name__)

    async def book(
        self,
        reservation_code: str,
        idem_key: str,
        reservation_snapshot: dict[str, Any] | None = None,
    ) -> SupplierBookingResult:
        if not self._endpoint:
            return SupplierBookingResult(
                status="FAILED", supplier_reservation_code=None, error_code="NO_ENDPOINT"
            )
        if not reservation_snapshot:
            return SupplierBookingResult(
                status="FAILED",
                supplier_reservation_code=None,
                error_code="MISSING_SNAPSHOT",
                error_message=(
                    "AmericaGroup gateway requiere datos de reserva "
                    "(pickup/dropoff codes, rate_id)."
                ),
            )

        pickup_code = (
            reservation_snapshot.get("pickup_location_code")
            or reservation_snapshot.get("pickup_office_code")
            or reservation_snapshot.get("pickup_office_id")
        )
        dropoff_code = (
            reservation_snapshot.get("dropoff_location_code")
            or reservation_snapshot.get("dropoff_office_code")
            or reservation_snapshot.get("dropoff_office_id")
        )
        car_type = reservation_snapshot.get("acriss_code")
        rate_id = reservation_snapshot.get("supplier_car_product_id")
        pickup_dt = reservation_snapshot.get("pickup_datetime")
        dropoff_dt = reservation_snapshot.get("dropoff_datetime")
        booking_ref = reservation_snapshot.get("token_id") or reservation_code

        if not pickup_code or not dropoff_code:
            return SupplierBookingResult(
                status="FAILED",
                supplier_reservation_code=None,
                error_code="MISSING_OFFICE_CODES",
            )

        xml_payload = self._build_xml(
            reservation_code=reservation_code,
            pickup_code=pickup_code,
            dropoff_code=dropoff_code,
            car_type=car_type,
            rate_id=rate_id,
            pickup_dt=pickup_dt,
            dropoff_dt=dropoff_dt,
            booking_reference=booking_ref,
            reservation_snapshot=reservation_snapshot,
        )
        params = {"XML": xml_payload}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(self._endpoint, params=params)
        except httpx.TimeoutException as exc:
            return SupplierBookingResult(
                status="FAILED",
                supplier_reservation_code=None,
                error_code="TIMEOUT",
                error_message=str(exc),
            )
        except httpx.HTTPError as exc:
            return SupplierBookingResult(
                status="FAILED",
                supplier_reservation_code=None,
                error_code="HTTP_ERROR",
                error_message=str(exc),
            )

        if not response.is_success:
            return SupplierBookingResult(
                status="FAILED",
                supplier_reservation_code=None,
                error_code="NON_2XX",
                error_message=response.text,
                http_status=response.status_code,
            )

        conf_id = self._extract_conf_id(response.text)
        if not conf_id:
            self._logger.warning(
                "AmericaGroup: missing ConfID in response",
                extra={"reservation_code": reservation_code},
            )
            return SupplierBookingResult(
                status="FAILED",
                supplier_reservation_code=None,
                payload={"raw": response.text},
                error_code="NO_CONF_ID",
            )

        return SupplierBookingResult(
            status="SUCCESS",
            supplier_reservation_code=conf_id,
            payload={"raw": response.text},
            http_status=response.status_code,
        )

    def _build_xml(
        self,
        reservation_code: str,
        pickup_code: Any,
        dropoff_code: Any,
        car_type: Any,
        rate_id: Any,
        pickup_dt: Any,
        dropoff_dt: Any,
        booking_reference: str,
        reservation_snapshot: dict[str, Any],
    ) -> str:
        root = Element("OTA_VehResRQ", Version="1.00")
        pos = SubElement(root, "POS")
        source = SubElement(pos, "Source")
        requestor = SubElement(source, "RequestorID")
        requestor.set("ID", self._requestor_id)

        booking_ref = SubElement(root, "BookingReferenceID")
        unique_id = SubElement(booking_ref, "UniqueID_Type")
        unique_id.set("ID", booking_reference)

        core = SubElement(root, "VehResRQCore")
        rental_core = SubElement(core, "VehRentalCore")
        rental_core.set("PickUpDateTime", str(pickup_dt or ""))
        rental_core.set("ReturnDateTime", str(dropoff_dt or ""))
        SubElement(rental_core, "PickUpLocation").set("LocationCode", str(pickup_code))
        SubElement(rental_core, "ReturnLocation").set("LocationCode", str(dropoff_code))

        # VehPref
        veh_pref = SubElement(core, "VehPref")
        veh_pref.set("VendorCarType", car_type)
        SubElement(veh_pref, "VehClass", car_type)
        SubElement(veh_pref, "VehType")

        # RateQualifier
        rate_qualifier = SubElement(core, "RateQualifier")
        if rate_id:
            rate_qualifier.set("VendorRateID", str(rate_id))

        # Customer
        customer = SubElement(core, "Customer")
        primary = SubElement(customer, "Primary")
        person_name = SubElement(primary, "PersonName")
        
        # Extract from snapshot or use defaults
        first_name = reservation_snapshot.get("first_name") or "Customer"
        last_name = reservation_snapshot.get("last_name") or "Primary"
        email_val = (
            reservation_snapshot.get("customer_email") or "reservations@mexicocarrental.com.mx"
        )
        
        SubElement(person_name, "GivenName", first_name)
        SubElement(person_name, "Surname", last_name)
        email = SubElement(primary, "Email")
        SubElement(email, "Value", email_val)

        # Serialize
        xml_bytes = tostring(root, encoding="utf-8", xml_declaration=True)
        return xml_bytes.decode()

    async def confirm_booking(self, reservation_code: str, details: dict[str, Any]) -> str:
        """
        Legacy compatibility.
        """
        result = await self.book(
            reservation_code=reservation_code,
            idem_key=f"compat-{reservation_code}",
            reservation_snapshot=details,
        )
        if result.status == "SUCCESS":
            return result.supplier_reservation_code or "SUCCESS"
        raise Exception(result.error_message or "AmericaGroup booking failed")

    def _extract_conf_id(self, xml_str: str) -> str | None:
        try:
            root = fromstring(xml_str)
            conf_nodes = root.findall(".//ConfID")
            for node in conf_nodes:
                conf_id = node.attrib.get("ID")
                if conf_id:
                    return conf_id
        except Exception:
            return None
        return None
