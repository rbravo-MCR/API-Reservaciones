import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.infrastructure.gateways.mex_group_gateway import MexGroupGateway


class TestMexGroupGateway(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.gateway = MexGroupGateway(
            endpoint="http://api.mexgroup.com",
            user="user",
            password="pwd"
        )
        self.snapshot = {
            "pickup_date": "2023-10-01",
            "pickup_time": "10:00",
            "dropoff_date": "2023-10-05",
            "dropoff_time": "10:00",
            "pickup_location_code": "MEX",
            "supplier_specific_data": {
                "rate_code": "R1",
                "class_code": "C1",
                "rate_id": "ID1"
            },
            "customer": {
                "first_name": "John",
                "last_name": "Doe"
            }
        }

    @patch("httpx.AsyncClient")
    async def test_book_success(self, mock_client_cls):
        # Mock Login Response
        mock_login_resp = MagicMock()
        mock_login_resp.status_code = 200
        mock_login_resp.json.return_value = {
            "type": "success",
            "data": {"token": "TOK123"}
        }
        mock_login_resp.raise_for_status = MagicMock()

        # Mock Reserve Response
        mock_res_resp = MagicMock()
        mock_res_resp.status_code = 200
        mock_res_resp.is_success = True
        mock_res_resp.json.return_value = {
            "data": {"noConfirmation": "CONF-MEX-001"}
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.side_effect = [mock_login_resp, mock_res_resp]
        mock_client_cls.return_value = mock_client

        result = await self.gateway.book("RES1", "key", self.snapshot)

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.supplier_reservation_code, "CONF-MEX-001")
        
        # Verify calls
        calls = mock_client.post.call_args_list
        # 1. Login
        self.assertIn("login", calls[0].args[0])
        # 2. Reserve
        self.assertIn("reserve", calls[1].args[0])
        self.assertEqual(calls[1].kwargs["headers"]["Authorization"], "Bearer TOK123")
        self.assertEqual(calls[1].kwargs["json"]["rate_code"], "R1")

    @patch("httpx.AsyncClient")
    async def test_auth_fail(self, mock_client_cls):
        # Mock Login Fail
        mock_login_resp = MagicMock()
        mock_login_resp.status_code = 401
        mock_login_resp.raise_for_status.side_effect = Exception("401 Unauthorized")

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_login_resp
        mock_client_cls.return_value = mock_client

        result = await self.gateway.book("RES1", "key", self.snapshot)

        self.assertEqual(result.status, "FAILED")
        self.assertEqual(result.error_code, "AUTH_ERROR")
