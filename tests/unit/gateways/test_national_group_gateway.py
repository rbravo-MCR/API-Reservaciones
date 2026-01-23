import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.infrastructure.gateways.national_group_gateway import NationalGroupGateway


class TestNationalGroupGateway(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.gateway = NationalGroupGateway(
            endpoint="http://national.api/v1",
            token="fake-token"
        )
        self.snapshot = {
            "pickup_date": "2023-10-10",
            "pickup_time": "10:00:00",
            "dropoff_date": "2023-10-15",
            "dropoff_time": "10:00:00",
            "pickup_location_code": "NAT01",
            "dropoff_location_code": "NAT01",
            "acriss_code": "MDMR",
            "category_name": "Mini",
            "customer": {
                "first_name": "Bob",
                "last_name": "Smith"
            }
        }

    @patch("httpx.AsyncClient")
    async def test_book_success(self, mock_client_cls):
        # Mock Reserve Response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_success = True
        mock_resp.json.return_value = {
            "data": {"id": "NAT-CONF-123"}
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        result = await self.gateway.book("RES1", "key", self.snapshot)

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.supplier_reservation_code, "NAT-CONF-123")
        
        # Verify call
        args, kwargs = mock_client.post.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer fake-token")
        self.assertEqual(kwargs["json"]["office_pickup"], "NAT01")
        self.assertEqual(kwargs["json"]["sipp_code"], "MDMR")

    @patch("httpx.AsyncClient")
    async def test_book_http_error(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.is_success = False
        mock_resp.text = "Bad Request"

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        result = await self.gateway.book("RES1", "key", self.snapshot)

        self.assertEqual(result.status, "FAILED")
        self.assertEqual(result.error_code, "HTTP_ERROR")
