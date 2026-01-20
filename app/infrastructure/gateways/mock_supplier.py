import asyncio
from typing import Any

from app.application.interfaces.supplier_gateway import SupplierGateway


class MockSupplierAdapter(SupplierGateway):
    async def confirm_booking(self, reservation_code: str, details: dict[str, Any]) -> str:
        # Simulate network latency
        await asyncio.sleep(0.5)
        
        # Simulate random failure (10% chance) - Disabled for happy path testing
        # if random.random() < 0.1:
        #     raise Exception("Supplier Timeout")
            
        # Return a fake supplier code
        return f"SUP-{reservation_code}-OK"
