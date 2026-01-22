import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, Optional
from xml.sax.saxutils import escape

import httpx
from app.application.interfaces.supplier_gateway import SupplierGateway, SupplierBookingResult

logger = logging.getLogger(__name__)

class CentauroAdapter(SupplierGateway):
    def __init__(self, base_url: str, login: str, password: str, agency: int):
        self.base_url = base_url
        self.login = login
        self.password = password
        self.agency = agency

    async def book(
        self,
        reservation_code: str,
        idem_key: str,
        reservation_snapshot: Optional[Dict[str, Any]] = None,
    ) -> SupplierBookingResult:
        """
        Migrated from CentauroRepository.php (insertReservation).
        """
        if not reservation_snapshot:
            return SupplierBookingResult(
                status="FAILED",
                error_code="MISSING_SNAPSHOT",
                error_message="Centauro requires a full reservation snapshot"
            )

        try:
            xml_payload = self._build_reservation_xml(reservation_snapshot)
            
            params = {
                "login": self.login,
                "pwd": self.password,
                "agency": self.agency,
                "action": 1,
                "xml": xml_payload
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self.base_url, data=params)
                response.raise_for_status()
                
                return self._parse_response(response.text)
        except Exception as e:
            logger.error(f"Centauro booking error: {e}", exc_info=True)
            return SupplierBookingResult(
                status="FAILED",
                error_code="CENTAURO_ERROR",
                error_message=str(e)
            )

    def _build_reservation_xml(self, d: Dict[str, Any]) -> str:
        """
        Replicates buildReservationXml logic from legacy PHP.
        """
        root = ET.Element("RESERVATION")
        header = ET.SubElement(root, "HEADER")
        
        if d.get("agency_id"):
            ET.SubElement(header, "AGENCY_ID").text = str(d["agency_id"])
        
        ET.SubElement(header, "CODE").text = escape(str(d.get("reservation_code", "")[:20]))
        
        # Passenger
        who = ET.SubElement(ET.SubElement(header, "WHO"), "CONTACT_DATA")
        driver = d.get("drivers", [{}])[0]
        ET.SubElement(who, "NAME").text = escape(driver.get("first_name", ""))
        ET.SubElement(who, "SURNAME").text = escape(driver.get("last_name", ""))
        
        # Offices
        where = ET.SubElement(header, "WHERE")
        pickup = ET.SubElement(ET.SubElement(where, "PICKUP"), "SERVICE_POINT_PICKUP")
        ET.SubElement(pickup, "CODE").text = escape(str(d.get("pickup_office_code", "")))
        
        dropoff = ET.SubElement(ET.SubElement(where, "RETURN"), "SERVICE_POINT_RETURN")
        ET.SubElement(dropoff, "CODE").text = escape(str(d.get("dropoff_office_code", "")))
        
        # Dates
        when = ET.SubElement(header, "WHEN")
        ET.SubElement(when, "CREATION_DATE").text = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        ET.SubElement(when, "START_DATE").text = self._format_date(d.get("pickup_datetime"))
        ET.SubElement(when, "END_DATE").text = self._format_date(d.get("dropoff_datetime"))
        
        # Flight
        ET.SubElement(ET.SubElement(header, "FLIGHT"), "NUMBER").text = escape(d.get("flight_number", ""))
        
        # Car group
        ET.SubElement(ET.SubElement(root, "CAR"), "PROVIDER_CATEGORY").text = escape(str(d.get("acriss_code", "")))
        
        # Net Price
        if d.get("supplier_cost_total"):
            ET.SubElement(ET.SubElement(root, "TOTAL"), "NET").text = str(d["supplier_cost_total"])

        return ET.tostring(root, encoding="unicode")

    def _format_date(self, dt_str: Optional[str]) -> str:
        if not dt_str:
            return ""
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            return dt.strftime("%d/%m/%Y %H:%M:%S")
        except:
            return dt_str

    def _parse_response(self, response_xml: str) -> SupplierBookingResult:
        try:
            root = ET.fromstring(response_xml)
            # Centauro usually returns confirmation in a specific tag
            # Based on legacy experience, it might be <ID_RESERVATION> or similar
            conf_elem = root.find(".//ID_RESERVATION") or root.find(".//CODE")
            
            if conf_elem is not None and conf_elem.text:
                return SupplierBookingResult(
                    status="SUCCESS",
                    supplier_reservation_code=conf_elem.text,
                    payload={"raw_xml": response_xml}
                )
            
            return SupplierBookingResult(
                status="FAILED",
                error_code="CENTAURO_REJECTED",
                error_message="No confirmation ID in XML response",
                payload={"raw_xml": response_xml}
            )
        except Exception as e:
            return SupplierBookingResult(
                status="FAILED",
                error_code="CENTAURO_PARSE_ERROR",
                error_message=f"Failed to parse Centauro response: {e}"
            )
