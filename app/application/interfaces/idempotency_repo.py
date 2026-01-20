from dataclasses import dataclass
from typing import Any


@dataclass
class IdempotencyRecord:
    scope: str
    idem_key: str
    request_hash: str
    response_json: dict[str, Any]
    http_status: int
    reference_reservation_code: str | None = None


class IdempotencyRepo:
    async def get(self, scope: str, idem_key: str) -> IdempotencyRecord | None:
        raise NotImplementedError

    async def save(self, record: IdempotencyRecord) -> None:
        raise NotImplementedError
