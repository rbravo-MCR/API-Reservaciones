from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.interfaces.receipt_query import (
    ReceiptContact,
    ReceiptData,
    ReceiptDriver,
    ReceiptPayment,
    ReceiptQuery,
)
from app.infrastructure.db.tables import (
    payments,
    reservation_contacts,
    reservation_drivers,
    reservations,
)


class ReceiptQuerySQL(ReceiptQuery):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _fetch_office(self, office_id: int) -> dict | None:
        stmt = text("SELECT id, code, name FROM offices WHERE id = :id LIMIT 1")
        result = await self._session.execute(stmt, {"id": office_id})
        row = result.mappings().first()
        return dict(row) if row else None

    async def _fetch_supplier(self, supplier_id: int) -> dict | None:
        stmt = text("SELECT id, name FROM suppliers WHERE id = :id LIMIT 1")
        result = await self._session.execute(stmt, {"id": supplier_id})
        row = result.mappings().first()
        return dict(row) if row else None

    async def _fetch_car_product(self, product_id: int | None) -> dict | None:
        if product_id is None:
            return None
        stmt = text(
            "SELECT id, car_category_id, external_code "
            "FROM supplier_car_products WHERE id = :id LIMIT 1"
        )
        result = await self._session.execute(stmt, {"id": product_id})
        row = result.mappings().first()
        return dict(row) if row else None

    async def get_receipt(self, reservation_code: str) -> ReceiptData | None:
        res_stmt = (
            select(reservations)
            .where(reservations.c.reservation_code == reservation_code)
            .limit(1)
        )
        res_result = await self._session.execute(res_stmt)
        res_row = res_result.mappings().first()
        if not res_row or not res_row.get("supplier_reservation_code"):
            return None

        contacts_stmt = select(reservation_contacts).where(
            reservation_contacts.c.reservation_code == reservation_code
        )
        drivers_stmt = select(reservation_drivers).where(
            reservation_drivers.c.reservation_code == reservation_code
        )
        payments_stmt = (
            select(payments)
            .where(payments.c.reservation_code == reservation_code)
            .order_by(payments.c.id.desc())
            .limit(1)
        )

        contacts_rows = (await self._session.execute(contacts_stmt)).mappings().all()
        drivers_rows = (await self._session.execute(drivers_stmt)).mappings().all()
        payment_row = (await self._session.execute(payments_stmt)).mappings().first()
        pickup_office = await self._fetch_office(res_row["pickup_office_id"])
        dropoff_office = await self._fetch_office(res_row["dropoff_office_id"])
        supplier = await self._fetch_supplier(res_row["supplier_id"])
        car_product = await self._fetch_car_product(res_row["supplier_car_product_id"])

        contacts = [
            ReceiptContact(
                contact_type=row["contact_type"],
                full_name=row["full_name"],
                email=row["email"],
                phone=row["phone"],
            )
            for row in contacts_rows
        ]
        drivers = [
            ReceiptDriver(
                is_primary_driver=bool(row["is_primary_driver"]),
                first_name=row["first_name"],
                last_name=row["last_name"],
                email=row["email"],
                phone=row["phone"],
                date_of_birth=row["date_of_birth"],
                driver_license_number=row["driver_license_number"],
            )
            for row in drivers_rows
        ]

        receipt_payment = ReceiptPayment(
            payment_status=res_row["payment_status"],
            provider=payment_row["provider"] if payment_row else "stripe",
            brand=None,
            last4=None,
        )

        return ReceiptData(
            reservation_code=res_row["reservation_code"],
            status=res_row["status"],
            supplier_reservation_code=res_row["supplier_reservation_code"],
            pickup_office_id=res_row["pickup_office_id"],
            pickup_office_code=pickup_office.get("code") if pickup_office else None,
            pickup_office_name=pickup_office.get("name") if pickup_office else None,
            pickup_datetime=res_row["pickup_datetime"],
            dropoff_office_id=res_row["dropoff_office_id"],
            dropoff_office_code=dropoff_office.get("code") if dropoff_office else None,
            dropoff_office_name=dropoff_office.get("name") if dropoff_office else None,
            dropoff_datetime=res_row["dropoff_datetime"],
            car_category_id=res_row["car_category_id"],
            acriss_code=car_product.get("external_code") if car_product else res_row["acriss_code"],
            supplier_car_product_id=res_row["supplier_car_product_id"],
            contacts=contacts,
            drivers=drivers,
            public_price_total=Decimal(res_row["public_price_total"]),
            taxes_total=Decimal(res_row["taxes_total"]),
            fees_total=Decimal(res_row["fees_total"]),
            discount_total=Decimal(res_row["discount_total"]),
            commission_total=Decimal(res_row["commission_total"]),
            supplier_cost_total=Decimal(res_row["supplier_cost_total"]),
            currency_code=res_row["currency_code"],
            payment=receipt_payment,
            supplier_id=res_row["supplier_id"],
            supplier_name=supplier.get("name") if supplier else None,
            created_at=res_row["pickup_datetime"],
            supplier_confirmed_at=res_row["supplier_confirmed_at"]
            or res_row["pickup_datetime"],
        )
