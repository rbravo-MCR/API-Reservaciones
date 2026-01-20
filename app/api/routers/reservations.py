from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.api.dependencies import get_use_cases
from app.api.schemas.reservations import (
    CreateReservationRequest,
    CreateReservationResponse,
    PayReservationRequest,
    PayReservationResponse,
    ReceiptResponse,
)

router = APIRouter()

@router.post(
    "/reservations",
    response_model=CreateReservationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_reservation(
    payload: CreateReservationRequest,
    idem_key: str = Header(default=None, convert_underscores=False, alias="Idempotency-Key"),
    use_cases=Depends(get_use_cases),
) -> CreateReservationResponse:
    if not idem_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required",
        )
    return await use_cases["create_reservation"].execute(request=payload, idem_key=idem_key)


@router.post(
    "/reservations/{reservation_code}/pay",
    response_model=PayReservationResponse,
    status_code=status.HTTP_200_OK,
)
async def pay_reservation(
    reservation_code: str,
    payload: PayReservationRequest,
    idem_key: str = Header(default=None, convert_underscores=False, alias="Idempotency-Key"),
    use_cases=Depends(get_use_cases),
) -> PayReservationResponse:
    if not idem_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required",
        )
    return await use_cases["pay_reservation"].execute(
        reservation_code=reservation_code,
        request=payload,
        idem_key=idem_key,
    )


@router.post("/webhooks/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    use_cases=Depends(get_use_cases),
) -> dict:
    raw_body = await request.body()
    signature = request.headers.get("Stripe-Signature")
    await use_cases["handle_webhook"].execute(raw_body=raw_body, signature=signature)
    return {}


@router.get(
    "/reservations/{reservation_code}/receipt",
    response_model=ReceiptResponse,
    status_code=status.HTTP_200_OK,
)
async def get_receipt(
    reservation_code: str,
    use_cases=Depends(get_use_cases),
) -> ReceiptResponse:
    return await use_cases["get_receipt"].execute(reservation_code=reservation_code)
