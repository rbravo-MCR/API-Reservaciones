from typing import Dict, Tuple

from app.application.interfaces.supplier_gateway import SupplierGateway
# Importamos la Factory solo para typing si es necesario, o usamos Any para evitar ciclos circulares si están en mismo paquete
# from app.infrastructure.gateways.factory import SupplierGatewayFactory 

class SupplierGatewaySelector:
    def __init__(
        self,
        default_gateway: SupplierGateway,
        mapping: Dict[Tuple[int, str], SupplierGateway] | None = None,
        factory = None, # SupplierGatewayFactory
    ):
        self._default = default_gateway
        self._mapping = mapping or {}
        self._factory = factory

    def register(self, supplier_id: int, country_code: str, gateway: SupplierGateway) -> None:
        self._mapping[(supplier_id, country_code.upper())] = gateway

    def for_supplier(self, supplier_id: int, country_code: str | None) -> SupplierGateway | None:
        # 1. Intentar match específico (ID + Country)
        if country_code:
            key = (supplier_id, country_code.upper())
            if key in self._mapping:
                return self._mapping[key]
        
        # 2. Intentar usar la Factory si está disponible (ID puro)
        if self._factory:
            return self._factory.get_adapter(str(supplier_id))

        # 3. Fallback genérico
        fallback_key = (supplier_id, "*")
        return self._mapping.get(fallback_key, self._default)