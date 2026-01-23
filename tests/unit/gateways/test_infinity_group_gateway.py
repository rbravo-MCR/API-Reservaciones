import unittest
import urllib.parse
from unittest.mock import AsyncMock, MagicMock, patch

from app.infrastructure.gateways.infinity_group_gateway import InfinityGroupGateway


class TestInfinityGroupGateway(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.gateway = InfinityGroupGateway(
            endpoint="http://test.infinity.com/ota",
            requestor_id="99"
        )
        self.snapshot = {
            "customer": {
                "first_name": "Jane",
                "last_name": "Doe",
            },
            "pickup_date": "2023-11-01",
            "pickup_time": "10:00",
            "dropoff_date": "2023-11-05",
            "dropoff_time": "10:00",
            "pickup_location_code": "CUN",
            "dropoff_location_code": "CUN",
            "supplier_specific_data": {
                "car_type": "ECAR",
                "vendor_rate_id": "RATE123"
            },
            "token_id": "RES999"
        }

    @patch("httpx.AsyncClient")
    async def test_book_success(self, mock_client_cls):
        # Mock Response XML Success
        success_xml = """<?xml version="1.0"?>
        <OTA_VehResRS Version="1.00">
            <Success/>
            <VehResRSCore>
                <VehReservation>
                    <VehSegmentCore>
                        <ConfID ID="CONF-12345" Type="14"/>
                    </VehSegmentCore>
                </VehReservation>
            </VehResRSCore>
        </OTA_VehResRS>"""
        
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_success = True
        mock_resp.text = success_xml
        
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        result = await self.gateway.book("RES999", "key", self.snapshot)

        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.supplier_reservation_code, "CONF-12345")
        
        # Verify URL params
        args, kwargs = mock_client.get.call_args
        url = args[0]
        self.assertIn("XML=", url)
        self.assertIn("RATE123", urllib.parse.unquote(url)) # vendor_rate_id inside
        self.assertIn("ECAR", urllib.parse.unquote(url))    # car_type inside

    @patch("httpx.AsyncClient")
    async def test_book_supplier_error(self, mock_client_cls):
        # Mock Response XML Error
        error_xml = """<?xml version="1.0"?>
        <OTA_VehResRS Version="1.00">
            <Errors>
                <Error ShortText="Vehicle not available"/>
            </Errors>
        </OTA_VehResRS>"""
        
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_success = True
        mock_resp.text = error_xml
        
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        result = await self.gateway.book("RES999", "key", self.snapshot)

        self.assertEqual(result.status, "FAILED")
        self.assertEqual(result.error_code, "SUPPLIER_ERROR")
        self.assertIn("Vehicle not available", result.error_message)

    @patch("httpx.AsyncClient")
    async def test_missing_data(self, mock_client_cls):
        # Snapshot missing supplier data
        bad_snapshot = {"customer": {}}
        
        result = await self.gateway.book("RES", "key", bad_snapshot)
        
        self.assertEqual(result.status, "FAILED")
        self.assertEqual(result.error_code, "MISSING_SUPPLIER_DATA")
