from typing import Dict, Tuple

from app.application.interfaces.supplier_gateway import SupplierGateway


class SupplierGatewaySelector:
    def __init__(
        self,
        default_gateway: SupplierGateway,
        mapping: Dict[Tuple[int, str], SupplierGateway] | None = None,
    ):
        self._default = default_gateway
        # mapping by (supplier_id, country_code_upper)
        self._mapping = mapping or {}

    def register(self, supplier_id: int, country_code: str, gateway: SupplierGateway) -> None:
        self._mapping[(supplier_id, country_code.upper())] = gateway

    def for_supplier(self, supplier_id: int, country_code: str | None) -> SupplierGateway | None:
        if not country_code:
            return None
        key = (supplier_id, country_code.upper())
        if key in self._mapping:
            return self._mapping[key]
        fallback_key = (supplier_id, "*")
        return self._mapping.get(fallback_key, self._default)
