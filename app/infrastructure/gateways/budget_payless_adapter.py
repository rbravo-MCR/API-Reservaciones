import logging
from datetime import datetime
from typing import Any, Dict, Optional

import httpx

from app.application.interfaces.supplier_gateway import SupplierBookingResult, SupplierGateway

logger = logging.getLogger(__name__)

class BudgetPaylessAdapter(SupplierGateway):
    def __init__(
        self, 
        base_url: str, 
        username: str, 
        password: str, 
        client_id: str, 
        client_secret: str,
        token_ttl: int = 3600
    ):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_ttl = token_ttl
        self._token: Optional[str] = None
        self._token_expires: Optional[datetime] = None

    async def _get_token(self) -> str:
        # Simple in-memory token caching for this slice
        if self._token and self._token_expires and datetime.now() < self._token_expires:
            return self._token

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/Authenticate/login",
                json={
                    "username": self.username,
                    "password": self.password,
                },
                headers={"Content-Type": "application/json-patch+json"}
            )
            response.raise_for_status()
            data = response.json()
            self._token = data.get("token") or data.get("accessToken") or data.get("jwt")
            if not self._token:
                raise RuntimeError("No token in Budget/Payless response")
            
            # We assume the token is valid for the TTL
            from datetime import timedelta
            self._token_expires = datetime.now() + timedelta(seconds=self.token_ttl - 60)
            return self._token

    async def _request(self, method: str, path: str, query: Optional[Dict] = None, body: Optional[Dict] = None) -> Any:
        token = await self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "text/plain",
        }
        
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        if query:
            params.update(query)

        async with httpx.AsyncClient(timeout=30.0) as client:
            if method.upper() == "GET":
                response = await client.get(f"{self.base_url}{path}", params=params, headers=headers)
            else:
                if body:
                    headers["Content-Type"] = "application/json-patch+json"
                    response = await client.post(f"{self.base_url}{path}", json=body, headers=headers)
                else:
                    response = await client.post(f"{self.base_url}{path}", params=params, headers=headers)
            
            if response.status_code == 401:
                self._token = None # Force re-auth on next try
                
            response.raise_for_status()
            return response.json()

    async def book(
        self,
        reservation_code: str,
        idem_key: str,
        reservation_snapshot: Optional[Dict[str, Any]] = None,
    ) -> SupplierBookingResult:
        """
        Migrated from BudgetPaylessRepository.php (createReservation).
        """
        if not reservation_snapshot:
            return SupplierBookingResult(
                status="FAILED",
                error_code="MISSING_SNAPSHOT",
                error_message="Budget/Payless requires a full reservation snapshot"
            )

        try:
            # The legacy PHP repository implies a flow: selectVehicle -> selectCoverages -> create
            # For simplicity in the first pass of the port, we assume the snapshot contains
            # the necessary payload for the create endpoint.
            
            # In a real scenario, we might need to perform the intermediate steps here
            # or ensure the application layer provides the transaction_id.
            
            payload = self._map_to_budget_payload(reservation_snapshot)
            result = await self._request("POST", "/v4/reservation/create", body=payload)
            
            # Legacy mapping for confirmation number
            conf_number = result.get("reservation_number") or result.get("confirmation_number")
            
            return SupplierBookingResult(
                status="SUCCESS",
                supplier_reservation_code=str(conf_number) if conf_number else "BUDGET-UNKNOWN",
                payload=result
            )
        except Exception as e:
            logger.error(f"Budget/Payless booking error: {e}", exc_info=True)
            return SupplierBookingResult(
                status="FAILED",
                error_code="BUDGET_PAYLESS_ERROR",
                error_message=str(e)
            )

    def _map_to_budget_payload(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        # Implementation of mapping rules found in legacy or provided by analyst
        # This is a placeholder for the actual mapping logic
        return {
            "transaction_id": snapshot.get("transaction_id", 0),
            "first_name": snapshot.get("drivers", [{}])[0].get("first_name", ""),
            "last_name": snapshot.get("drivers", [{}])[0].get("last_name", ""),
            "email": snapshot.get("drivers", [{}])[0].get("email", ""),
            "phone": snapshot.get("drivers", [{}])[0].get("phone", ""),
            # ... other fields
        }
