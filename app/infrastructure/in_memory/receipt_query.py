from datetime import datetime

from app.application.interfaces.receipt_query import (
    ReceiptContact,
    ReceiptData,
    ReceiptDriver,
    ReceiptPayment,
    ReceiptQuery,
)
from app.infrastructure.in_memory.payment_repo import InMemoryPaymentRepo
from app.infrastructure.in_memory.reservation_repo import InMemoryReservationRepo
from app.infrastructure.in_memory.supplier_request_repo import InMemorySupplierRequestRepo


class InMemoryReceiptQuery(ReceiptQuery):
    def __init__(
        self,
        reservation_repo: InMemoryReservationRepo,
        payment_repo: InMemoryPaymentRepo,
        supplier_request_repo: InMemorySupplierRequestRepo,
    ) -> None:
        self._reservation_repo = reservation_repo
        self._payment_repo = payment_repo
        self._supplier_request_repo = supplier_request_repo

    async def get_receipt(self, reservation_code: str) -> ReceiptData | None:
        reservation = self._reservation_repo.reservations.get(reservation_code)
        if not reservation:
            return None
        contacts = [
            ReceiptContact(
                contact_type=contact.contact_type,
                full_name=contact.full_name,
                email=contact.email,
                phone=contact.phone,
            )
            for contact in self._reservation_repo.contacts.get(reservation_code, [])
        ]
        drivers = [
            ReceiptDriver(
                is_primary_driver=driver.is_primary_driver,
                first_name=driver.first_name,
                last_name=driver.last_name,
                email=driver.email,
                phone=driver.phone,
                date_of_birth=driver.date_of_birth,
                driver_license_number=driver.driver_license_number,
            )
            for driver in self._reservation_repo.drivers.get(reservation_code, [])
        ]
        payments = self._payment_repo._by_reservation.get(reservation_code, [])
        payment_id = payments[-1] if payments else None
        payment = self._payment_repo._by_id[payment_id] if payment_id else None
        receipt_payment = ReceiptPayment(
            payment_status=reservation.payment_status,
            provider=payment.provider if payment else "stripe",
            brand=None,
            last4=None,
        )
        return ReceiptData(
            reservation_code=reservation.reservation_code,
            status=reservation.status,
            supplier_reservation_code=reservation.supplier_reservation_code or "",
            pickup_office_id=reservation.pickup_office_id,
            pickup_office_code=None,
            pickup_office_name=None,
            pickup_datetime=datetime.fromisoformat(reservation.pickup_datetime),
            dropoff_office_id=reservation.dropoff_office_id,
            dropoff_office_code=None,
            dropoff_office_name=None,
            dropoff_datetime=datetime.fromisoformat(reservation.dropoff_datetime),
            car_category_id=reservation.car_category_id,
            acriss_code=reservation.acriss_code,
            supplier_car_product_id=reservation.supplier_car_product_id,
            contacts=contacts,
            drivers=drivers,
            public_price_total=reservation.public_price_total,
            taxes_total=reservation.taxes_total,
            fees_total=reservation.fees_total,
            discount_total=reservation.discount_total,
            commission_total=reservation.commission_total,
            supplier_cost_total=reservation.supplier_cost_total,
            currency_code=reservation.currency_code,
            payment=receipt_payment,
            supplier_id=reservation.supplier_id,
            supplier_name=None,
            created_at=datetime.fromisoformat(reservation.pickup_datetime),
            supplier_confirmed_at=datetime.fromisoformat(
                reservation.supplier_confirmed_at or reservation.pickup_datetime
            ),
        )
