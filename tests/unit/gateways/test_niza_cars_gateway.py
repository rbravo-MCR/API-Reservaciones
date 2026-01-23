import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.infrastructure.gateways.niza_cars_gateway import NizaCarsGateway


class TestNizaCarsGateway(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.gateway = NizaCarsGateway(
            base_url="http://niza.test",
            company_code="NIZA",
            customer_code="CUST",
            username="user",
            password="pwd"
        )
        self.snapshot = {
            "pickup_date": "2023-11-01",
            "pickup_time": "10:00:00",
            "dropoff_date": "2023-11-05",
            "dropoff_time": "10:00:00",
            "pickup_location_code": "MEX1",
            "dropoff_location_code": "MEX1",
            "supplier_specific_data": {
                "Group": "A",
                "RateCode": "FF"
            },
            "customer": {
                "first_name": "Test",
                "last_name": "User"
            }
        }

    @patch("httpx.AsyncClient")
    async def test_book_success(self, mock_client_cls):
        # Mock SOAP Response with ID
        success_xml = """<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
            <soap:Body>
                <Create_ReservationResponse xmlns="http://www.jimpisoft.pt/Rentway_Reservations_WS/Create_Reservation">
                    <Create_ReservationResult>
                        <ReservationID>12345</ReservationID>
                        <Status>Confirmed</Status>
                    </Create_ReservationResult>
                </Create_ReservationResponse>
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
        self.assertEqual(result.supplier_reservation_code, "12345")
        
        # Verify call
        args, kwargs = mock_client.post.call_args
        self.assertIn("Create_Reservation", kwargs["headers"]["SOAPAction"])
        self.assertIn("<Group>A</Group>", kwargs["content"])

    @patch("httpx.AsyncClient")
    async def test_book_error(self, mock_client_cls):
        # Mock SOAP Response with Error
        error_xml = """<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
            <soap:Body>
                <Create_ReservationResponse>
                    <Create_ReservationResult>
                        <Error>Vehicle group not available</Error>
                    </Create_ReservationResult>
                </Create_ReservationResponse>
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
        self.assertIn("Vehicle group not available", result.error_message)
