from typing import Dict

from app.application.interfaces.supplier_gateway import SupplierGateway
from app.infrastructure.gateways.avis_adapter import AvisAdapter
from app.infrastructure.gateways.mock_supplier import MockSupplierAdapter


class SupplierGatewayFactory:
    def __init__(self, config: Dict[str, Dict[str, str]]):
        self.config = config
        self._adapters: Dict[str, SupplierGateway] = {}

    def get_adapter(self, supplier_id: str) -> SupplierGateway:
        # For simplicity in this slice, we map supplier_id to specific adapters
        # In production, this would be more dynamic (e.g., from DB)
        
        if supplier_id == "16": # Avis ID from legacy
            if "avis" not in self._adapters:
                avis_conf = self.config.get("avis", {})
                self._adapters["avis"] = AvisAdapter(
                    endpoint=avis_conf.get("endpoint", ""),
                    user=avis_conf.get("user", ""),
                    password=avis_conf.get("password", ""),
                    target=avis_conf.get("target", "Test")
                )
            return self._adapters["avis"]
        
        # Default to Mock for others
        if "mock" not in self._adapters:
            self._adapters["mock"] = MockSupplierAdapter()
        return self._adapters["mock"]
