import traceback

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.application.schemas import (
    CreateReservationRequest,
    CreateReservationResponse,
    ReservationReceiptResponse,
)
from app.application.use_cases.create_reservation import CreateReservationUseCase
from app.application.use_cases.get_receipt import GetReservationReceiptUseCase
from app.application.use_cases.handle_webhook import HandleStripeWebhookUseCase
from app.infrastructure.db.repository import ReservationRepository

router = APIRouter()

@router.post(
    "/reservations",
    response_model=CreateReservationResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_reservation(
    request: CreateReservationRequest,
    session: AsyncSession = Depends(get_db_session)
):
    repository = ReservationRepository(session)
    use_case = CreateReservationUseCase(repository)
    
    try:
        response = await use_case.execute(request)
        await session.commit()
        return response
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.get("/reservations/{code}/receipt", response_model=ReservationReceiptResponse)
async def get_reservation_receipt(
    code: str,
    session: AsyncSession = Depends(get_db_session)
):
    repository = ReservationRepository(session)
    use_case = GetReservationReceiptUseCase(repository)
    
    try:
        return await use_case.execute(code)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.post("/webhooks/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None),
    session: AsyncSession = Depends(get_db_session)
):
    payload = await request.body()
    repository = ReservationRepository(session)
    use_case = HandleStripeWebhookUseCase(repository)
    
    try:
        await use_case.execute(payload, stripe_signature)
        await session.commit()
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        traceback.print_exc()
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e
