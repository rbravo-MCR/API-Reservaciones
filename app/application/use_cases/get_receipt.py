from app.api.schemas.reservations import (
    Contact,
    Driver,
    OfficeSnapshot,
    PricingSnapshot,
    ReceiptPayment,
    ReceiptResponse,
    SupplierSnapshot,
    VehicleSnapshot,
)
from app.application.interfaces.receipt_query import ReceiptQuery


class GetReceiptUseCase:
    def __init__(self, receipt_query: ReceiptQuery) -> None:
        self._receipt_query = receipt_query

    async def execute(self, reservation_code: str) -> ReceiptResponse:
        data = await self._receipt_query.get_receipt(reservation_code)
        if not data:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Receipt for reservation {reservation_code} not found or not confirmed",
            )

        return ReceiptResponse(
            reservation_code=data.reservation_code,
            status=data.status,
            supplier_reservation_code=data.supplier_reservation_code,
            pickup=OfficeSnapshot(
                office_id=data.pickup_office_id,
                code=data.pickup_office_code,
                name=data.pickup_office_name,
                datetime=data.pickup_datetime,
            ),
            dropoff=OfficeSnapshot(
                office_id=data.dropoff_office_id,
                code=data.dropoff_office_code,
                name=data.dropoff_office_name,
                datetime=data.dropoff_datetime,
            ),
            vehicle=VehicleSnapshot(
                car_category_id=data.car_category_id,
                acriss_code=data.acriss_code,
                supplier_car_product_id=data.supplier_car_product_id,
            ),
            contacts=[
                Contact(
                    contact_type=c.contact_type,
                    full_name=c.full_name,
                    email=c.email,
                    phone=c.phone,
                )
                for c in data.contacts
            ],
            drivers=[
                Driver(
                    is_primary_driver=d.is_primary_driver,
                    first_name=d.first_name,
                    last_name=d.last_name,
                    email=d.email,
                    phone=d.phone,
                    date_of_birth=d.date_of_birth,
                    driver_license_number=d.driver_license_number,
                )
                for d in data.drivers
            ],
            pricing=PricingSnapshot(
                public_price_total=data.public_price_total,
                taxes_total=data.taxes_total,
                fees_total=data.fees_total,
                discount_total=data.discount_total,
                commission_total=data.commission_total,
                supplier_cost_total=data.supplier_cost_total,
                currency_code=data.currency_code,
            ),
            payment=ReceiptPayment(
                payment_status=data.payment.payment_status,
                provider=data.payment.provider,
                brand=data.payment.brand,
                last4=data.payment.last4,
            ),
            supplier=SupplierSnapshot(
                id=data.supplier_id,
                name=data.supplier_name,
            ),
            created_at=data.created_at,
            supplier_confirmed_at=data.supplier_confirmed_at,
        )
