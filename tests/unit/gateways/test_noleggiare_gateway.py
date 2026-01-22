import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from app.infrastructure.gateways.noleggiare_gateway import NoleggiareGateway

class TestNoleggiareGateway(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.gateway = NoleggiareGateway(
            endpoint="http://noleggiare.test",
            username="user",
            password="pwd",
            company="COMP"
        )
        self.snapshot = {
            "pickup_date": "2023-11-01",
            "pickup_time": "10:00:00",
            "dropoff_date": "2023-11-05",
            "dropoff_time": "10:00:00",
            "pickup_location_code": "FCO",
            "dropoff_location_code": "FCO",
            "supplier_specific_data": {
                "sipp_code": "MBMR"
            },
            "customer": {
                "first_name": "Mario",
                "last_name": "Rossi"
            }
        }

    @patch("httpx.AsyncClient")
    async def test_book_success(self, mock_client_cls):
        # Mock SOAP Response with ConfID
        success_xml = """<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
            <soap:Body>
                <OTA_VehResRS xmlns="http://www.opentravel.org/OTA/2003/05">
                    <Success/>
                    <VehResRSCore>
                        <VehReservation>
                            <VehSegmentCore>
                                <ConfID ID="NOL-12345" Type="14"/>
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

        result = await self.gateway.book("RES1", "key", self.snapshot)

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.supplier_reservation_code, "NOL-12345")
        
        # Verify call
        args, kwargs = mock_client.post.call_args
        self.assertIn('Code="MBMR"', kwargs["content"])
        self.assertIn('ID="user"', kwargs["content"])

    @patch("httpx.AsyncClient")
    async def test_book_ota_error(self, mock_client_cls):
        # Mock SOAP Response with OTA Error
        error_xml = """<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
            <soap:Body>
                <OTA_VehResRS xmlns="http://www.opentravel.org/OTA/2003/05">
                    <Errors>
                        <Error ShortText="Sold Out" Code="204"/>
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

        result = await self.gateway.book("RES1", "key", self.snapshot)

        self.assertEqual(result.status, "FAILED")
        self.assertIn("Sold Out", result.error_message)
