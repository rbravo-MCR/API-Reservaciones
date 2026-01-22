from collections import defaultdict

from app.application.interfaces.idempotency_repo import IdempotencyRecord, IdempotencyRepo


class InMemoryIdempotencyRepo(IdempotencyRepo):
    def __init__(self) -> None:
        self._records: dict[str, dict[str, IdempotencyRecord]] = defaultdict(dict)

    async def get(self, scope: str, idem_key: str) -> IdempotencyRecord | None:
        return self._records.get(scope, {}).get(idem_key)

    async def save(self, record: IdempotencyRecord) -> None:
        self._records[record.scope][record.idem_key] = record

