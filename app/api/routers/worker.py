from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_use_cases
from app.infrastructure.db.retry import retry_on_deadlock

router = APIRouter()


@router.post(
    "/workers/outbox/book-supplier/{reservation_code}",
    status_code=status.HTTP_200_OK,
)
async def process_outbox_book_supplier(
    reservation_code: str,
    use_cases: Annotated[dict, Depends(get_use_cases)],
    idem_key: str | None = Query(default=None),
    worker_id: str | None = Query(default=None, alias="worker-id"),
) -> dict:
    """
    Process outbox event for supplier booking with automatic deadlock retry.

    Handles concurrent outbox processing safely with retry logic.
    """
    if not idem_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idem key required for supplier booking",
        )

    async def execute_outbox():
        return await use_cases["process_outbox"].execute(
            reservation_code=reservation_code, idem_key=idem_key, worker_id=worker_id or "worker-1"
        )

    try:
        return await retry_on_deadlock(execute_outbox, max_attempts=3, base_delay=0.1)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
