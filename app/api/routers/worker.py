from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_use_cases

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
    if not idem_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idem key required for supplier booking",
        )
    return await use_cases["process_outbox"].execute(
        reservation_code=reservation_code, idem_key=idem_key, worker_id=worker_id or "worker-1"
    )
