import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from app.infrastructure.gateways.hertz_argentina_gateway import HertzArgentinaGateway

class TestHertzArgentinaGateway(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.gateway = HertzArgentinaGateway(
            base_url="http://test.com",
            auth_url="http://auth.com/token",
            username="user",
            password="pass",
            client_id="client",
            grant_type="password"
        )
        self.snapshot = {
            "customer": {
                "first_name": "John",
                "last_name": "Doe",
                "email": "john@example.com"
            },
            "dob": "1990-01-01",
            "pickup_date": "2023-10-10",
            "dropoff_date": "2023-10-15",
            "model": "EDAR",
            "deliveryPlace": "EZE"
        }

    @patch("httpx.AsyncClient")
    async def test_book_success(self, mock_client_cls):
        # Mock Auth Response
        mock_auth_resp = MagicMock()
        mock_auth_resp.status_code = 200
        mock_auth_resp.json.return_value = {"access_token": "fake-token"}
        mock_auth_resp.raise_for_status = MagicMock()

        # Mock Booking Response
        mock_book_resp = MagicMock()
        mock_book_resp.status_code = 200
        mock_book_resp.is_success = True
        mock_book_resp.json.return_value = {"id": "12345", "status": "CONFIRMED"}

        # Configurar el cliente mock
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.side_effect = [mock_auth_resp, mock_book_resp]
        mock_client_cls.return_value = mock_client

        result = await self.gateway.book("RES123", "key", self.snapshot)

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.supplier_reservation_code, "12345")
        
        # Verificar llamadas
        calls = mock_client.post.call_args_list
        # Debería haber 2 llamadas: Auth y Booking
        self.assertEqual(len(calls), 2)
        
        # 1. Auth
        auth_call = calls[0]
        self.assertEqual(auth_call.args[0], "http://auth.com/token")
        
        # 2. Booking
        booking_call = calls[1]
        self.assertEqual(booking_call.args[0], "http://test.com/Booking")
        self.assertIn("Authorization", booking_call.kwargs["headers"])
        self.assertEqual(booking_call.kwargs["headers"]["Authorization"], "Bearer fake-token")

    @patch("httpx.AsyncClient")
    async def test_book_auth_failure(self, mock_client_cls):
        # Mock Auth Response Failure
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        
        # Simular error en auth
        mock_client.post.side_effect = Exception("Auth Down")
        mock_client_cls.return_value = mock_client

        result = await self.gateway.book("RES123", "key", self.snapshot)

        self.assertEqual(result.status, "FAILED")
        self.assertEqual(result.error_code, "AUTH_ERROR")

    def test_calculate_age(self):
        # 1990-01-01 -> Debería ser > 30
        age = self.gateway._calculate_age("1990-01-01")
        self.assertGreater(age, 30)
        
        # Fecha inválida -> fallback 30
        age_invalid = self.gateway._calculate_age("invalid-date")
        self.assertEqual(age_invalid, 30)
