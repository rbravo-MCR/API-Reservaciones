import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any
from xml.sax.saxutils import escape

import httpx

from app.application.interfaces.supplier_gateway import SupplierGateway


class AvisAdapter(SupplierGateway):
    def __init__(self, endpoint: str, user: str, password: str, target: str = "Test"):
        self.endpoint = endpoint
        self.user = user
        self.password = password
        self.target = target

    async def confirm_booking(self, reservation_code: str, details: dict[str, Any]) -> str:
        """
        Migrated from AvisRepository.php (createReservation).
        Strictly for reservation confirmation.
        """
        # 1. Prepare Data (Mapping from details or defaults)
        pickup_code = escape(str(details.get("pickup_office_code", "MIA")))
        pickup_dt = escape(str(details.get("pickup_datetime", datetime.now().isoformat())))
        return_dt = escape(str(details.get("dropoff_datetime", datetime.now().isoformat())))
        email = escape(str(details.get("customer_email", "test@example.com")))
        first_name = escape(str(details.get("first_name", "QA")))
        last_name = escape(str(details.get("last_name", "Tester")))
        
        # 2. Build OTA_VehResRQ (Legacy Logic)
        ota_payload = self._build_ota_res_rq(
            pickup_code, pickup_dt, return_dt, email, first_name, last_name
        )
        
        # 3. Wrap in SOAP Envelope (Legacy Logic)
        soap_envelope = self._build_soap_envelope(ota_payload)
        
        # 4. Send Request
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    self.endpoint,
                    content=soap_envelope,
                    headers={"Content-Type": "text/xml; charset=utf-8"}
                )
                response.raise_for_status()
                return self._parse_confirmation_code(response.text)
            except Exception as e:
                # In a real scenario, we would log the raw XML for audit
                msg = f"Avis Supplier Error: {str(e)}"
                raise Exception(msg) from e

    async def book(
        self,
        reservation_code: str,
        idem_key: str,
        reservation_snapshot: dict[str, Any] | None = None,
    ) -> Any: # Returns SupplierBookingResult
        """
        Implementation for the complex architecture.
        """
        from app.application.interfaces.supplier_gateway import SupplierBookingResult
        
        details = reservation_snapshot or {}
        try:
            conf_code = await self.confirm_booking(reservation_code, details)
            return SupplierBookingResult(
                status="SUCCESS",
                supplier_reservation_code=conf_code,
                payload={"raw": "Avis booking successful"}
            )
        except Exception as e:
            return SupplierBookingResult(
                status="FAILED",
                error_code="AVIS_ERROR",
                error_message=str(e)
            )

    def _build_ota_res_rq(
        self, pickup_code, pickup_dt, return_dt, email, first_name, last_name
    ) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        return f"""
        <OTA_VehResRQ xmlns="http://www.opentravel.org/OTA/2003/05" 
                      Version="1.0" 
                      Target="{self.target}" 
                      TimeStamp="{timestamp}">
            <POS>
                <Source>
                    <RequestorID Type="1" ID="MexicoCarRental"/>
                </Source>
            </POS>
            <VehResRQCore>
                <VehRentalCore PickUpDateTime="{pickup_dt}" ReturnDateTime="{return_dt}">
                    <PickUpLocation LocationCode="{pickup_code}"/>
                </VehRentalCore>
                <Customer>
                    <Primary>
                        <PersonName>
                            <GivenName>{first_name}</GivenName>
                            <Surname>{last_name}</Surname>
                        </PersonName>
                        <Email>{email}</Email>
                    </Primary>
                </Customer>
                <VendorPref CompanyShortName="Avis"/>
            </VehResRQCore>
        </OTA_VehResRQ>
        """

    def _build_soap_envelope(self, payload: str) -> str:
        user = escape(self.user)
        password = escape(self.password)
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"
                   xmlns:ns="http://wsg.avis.com/wsbang/authInAny">
  <SOAP-ENV:Header>
    <ns:credentials>
      <ns:userID>{user}</ns:userID>
      <ns:password>{password}</ns:password>
    </ns:credentials>
  </SOAP-ENV:Header>
  <SOAP-ENV:Body>
    <ns:Request xmlns:ns="http://wsg.avis.com/wsbang">
      {payload}
    </ns:Request>
  </SOAP-ENV:Body>
</SOAP-ENV:Envelope>
"""

    def _parse_confirmation_code(self, response_xml: str) -> str:
        """
        Robust parsing for the confirmation ID.
        Handles namespaces by searching for local names.
        """
        try:
            # We use a simple approach to find the ConfID regardless of namespaces
            # In production, a more formal namespace mapping is preferred
            root = ET.fromstring(response_xml)
            
            # Search for UniqueID with Type="14" (Reservation) or ConfID
            # Avis usually returns it in VehResRSCore/VehReservation/UniqueID
            for elem in root.iter():
                # Strip namespace
                tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
                if tag == "UniqueID" and elem.get("Type") == "14":
                    return elem.get("ID", "AVIS-UNKNOWN")
                if tag == "ConfID":
                    return elem.text or "AVIS-UNKNOWN"
            
            # Fallback if not found but response was 200
            if "ConfID" in response_xml or "UniqueID" in response_xml:
                return "AVIS-CONF-MANUAL"
                
            return "AVIS-PENDING"
        except ET.ParseError:
            return "AVIS-ERROR-PARSE"
