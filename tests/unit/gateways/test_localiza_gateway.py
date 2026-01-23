import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.infrastructure.gateways.localiza_gateway import LocalizaGateway


class TestLocalizaGateway(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.gateway = LocalizaGateway(
            endpoint="http://test.localiza.com/ota",
            username="user",
            password="pwd",
            echo_token="ECHO123",
            requestor_id="REQ999"
        )
        self.snapshot = {
            "pickup_datetime": "2023-12-01T10:00:00",
            "dropoff_datetime": "2023-12-05T10:00:00",
            "pickup_location_code": "GRU",
            "customer": {
                "first_name": "Juan",
                "last_name": "Perez"
            },
            "supplier_specific_data": {
                "veh_size": "SIZ",
                "veh_category": "VEC"
            }
        }

    @patch("httpx.AsyncClient")
    async def test_book_success(self, mock_client_cls):
        # Mock Response SOAP Success
        success_xml = """<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
            <soap:Body>
                <OTA_VehResRS xmlns="http://www.opentravel.org/OTA/2003/05" Version="2.001">
                    <Success/>
                    <VehResRSCore>
                        <VehReservation>
                            <VehSegmentCore>
                                <ConfID ID="LOC-ABCDE" Type="14"/>
                            </VehSegmentCore>
                        </VehReservation>
                    </VehResRSCore>
                </OTA_VehResRS>
            </soap:Body>
        </soap:Envelope>"""
        
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_success = True
        mock_resp.text = success_xml
        
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        result = await self.gateway.book("RES100", "key", self.snapshot)

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.supplier_reservation_code, "LOC-ABCDE")
        
        # Verify Auth and Header
        args, kwargs = mock_client.post.call_args
        self.assertEqual(kwargs['auth'], ('user', 'pwd'))
        self.assertIn('OTA_VehResRQ', kwargs['headers']['SOAPAction'])

    @patch("httpx.AsyncClient")
    async def test_book_error(self, mock_client_cls):
        # Mock Response SOAP Error
        error_xml = """<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
            <soap:Body>
                <OTA_VehResRS xmlns="http://www.opentravel.org/OTA/2003/05">
                    <Errors>
                        <Error ShortText="No cars available"/>
                    </Errors>
                </OTA_VehResRS>
            </soap:Body>
        </soap:Envelope>"""
        
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_success = True
        mock_resp.text = error_xml
        
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        result = await self.gateway.book("RES100", "key", self.snapshot)

        self.assertEqual(result.status, "FAILED")
        self.assertEqual(result.error_code, "SUPPLIER_ERROR")
        self.assertIn("No cars available", result.error_message)
