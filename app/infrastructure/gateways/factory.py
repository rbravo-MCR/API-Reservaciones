from typing import Any, Dict

from app.application.interfaces.supplier_gateway import SupplierGateway
from app.infrastructure.gateways.avis_adapter import AvisAdapter
from app.infrastructure.gateways.europcar_group_gateway import EuropcarGroupGateway
from app.infrastructure.gateways.hertz_argentina_gateway import HertzArgentinaGateway
from app.infrastructure.gateways.infinity_group_gateway import InfinityGroupGateway
from app.infrastructure.gateways.localiza_gateway import LocalizaGateway
from app.infrastructure.gateways.mex_group_gateway import MexGroupGateway
from app.infrastructure.gateways.national_group_gateway import NationalGroupGateway
from app.infrastructure.gateways.niza_cars_gateway import NizaCarsGateway
from app.infrastructure.gateways.noleggiare_gateway import NoleggiareGateway
from app.infrastructure.gateways.mock_supplier import MockSupplierAdapter


class SupplierGatewayFactory:
    def __init__(self, config: Dict[str, Dict[str, Any]]):
        self.config = config
        self._adapters: Dict[str, SupplierGateway] = {}

    def get_adapter(self, supplier_id: str) -> SupplierGateway:
        # Normalización de ID
        sid = str(supplier_id)
        
        # Avis (16)
        if sid == "16":
            if "avis" not in self._adapters:
                conf = self.config.get("avis", {})
                self._adapters["avis"] = AvisAdapter(
                    endpoint=conf.get("endpoint", ""),
                    user=conf.get("user", ""),
                    password=conf.get("password", ""),
                    target=conf.get("target", "Test")
                )
            return self._adapters["avis"]

        # Europcar Group (1=Europcar, 93=Keddy, 109=Fox)
        if sid in ["1", "93", "109"]:
            if "europcar_group" not in self._adapters:
                conf = self.config.get("europcargroup", {})
                self._adapters["europcar_group"] = EuropcarGroupGateway(
                    endpoint=conf.get("endpoint", ""),
                    timeout_seconds=float(conf.get("timeout_seconds", 6.0)),
                )
            return self._adapters["europcar_group"]

        # Hertz Argentina (128)
        if sid == "128":
            if "hertz_ar" not in self._adapters:
                conf = self.config.get("hertzargentina", {})
                self._adapters["hertz_ar"] = HertzArgentinaGateway(
                    base_url=conf.get("base_url", ""),
                    auth_url=conf.get("auth_url", ""),
                    username=conf.get("username", ""),
                    password=conf.get("password", ""),
                    client_id=conf.get("client_id", ""),
                    grant_type=conf.get("grant_type", "password")
                )
            return self._adapters["hertz_ar"]

        # Infinity Group (106)
        if sid == "106":
            if "infinity" not in self._adapters:
                conf = self.config.get("infinity", {})
                self._adapters["infinity"] = InfinityGroupGateway(
                    endpoint=conf.get("endpoint", ""),
                    requestor_id=conf.get("requestor_id", "92")
                )
            return self._adapters["infinity"]

        # Localiza (No ID específico en legacy, usamos "localiza" o un ID asignado)
        if sid.lower() == "localiza":
            if "localiza" not in self._adapters:
                conf = self.config.get("localiza", {})
                self._adapters["localiza"] = LocalizaGateway(
                    endpoint=conf.get("endpoint", ""),
                    username=conf.get("username", ""),
                    password=conf.get("password", ""),
                    echo_token=conf.get("echo_token", ""),
                    requestor_id=conf.get("requestor_id", "")
                )
            return self._adapters["localiza"]

        # Mex Group (28)
        if sid == "28":
            if "mex" not in self._adapters:
                conf = self.config.get("mexgroup", {})
                self._adapters["mex"] = MexGroupGateway(
                    endpoint=conf.get("endpoint", ""),
                    user=conf.get("user", ""),
                    password=conf.get("password", "")
                )
            return self._adapters["mex"]

        # National Group (2, 82)
        if sid in ["2", "82"]:
            if "national" not in self._adapters:
                conf = self.config.get("nationalgroup", {})
                self._adapters["national"] = NationalGroupGateway(
                    endpoint=conf.get("endpoint", ""),
                    token=conf.get("token", "")
                )
            return self._adapters["national"]

        # Niza Cars (126)
        if sid == "126":
            if "niza" not in self._adapters:
                conf = self.config.get("nizacars", {})
                self._adapters["niza"] = NizaCarsGateway(
                    base_url=conf.get("base_url", ""),
                    company_code=conf.get("company", ""),
                    customer_code=conf.get("customer", ""),
                    username=conf.get("user", ""),
                    password=conf.get("pass", "")
                )
            return self._adapters["niza"]

        # Noleggiare (No ID en legacy, usamos "noleggiare")
        if sid.lower() == "noleggiare":
            if "noleggiare" not in self._adapters:
                conf = self.config.get("noleggiare", {})
                self._adapters["noleggiare"] = NoleggiareGateway(
                    endpoint=conf.get("endpoint", ""),
                    username=conf.get("username", ""),
                    password=conf.get("password", ""),
                    company=conf.get("company", "")
                )
            return self._adapters["noleggiare"]
        
        # Default to Mock
        if "mock" not in self._adapters:
            self._adapters["mock"] = MockSupplierAdapter()
        return self._adapters["mock"]
