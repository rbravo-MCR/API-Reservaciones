from dataclasses import asdict
from datetime import datetime
from typing import Sequence

from fastapi import HTTPException, status
from sqlalchemy import insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.interfaces.reservation_repo import (
    ContactInput,
    DriverInput,
    ReservationInput,
    ReservationRepo,
)
from app.infrastructure.db.tables import reservation_contacts, reservation_drivers, reservations


class ReservationRepoSQL(ReservationRepo):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _exists(self, table: str, entity_id: int | None) -> bool:
        if entity_id is None:
            return True
        stmt = text(f"SELECT 1 FROM {table} WHERE id = :id LIMIT 1")
        result = await self._session.execute(stmt, {"id": entity_id})
        return result.scalar() is not None

    async def _validate_references(self, reservation: ReservationInput) -> None:
        missing: list[str] = []
        checks = [
            ("supplier", "suppliers", reservation.supplier_id),
            ("pickup_office", "offices", reservation.pickup_office_id),
            ("dropoff_office", "offices", reservation.dropoff_office_id),
            ("car_category", "car_categories", reservation.car_category_id),
            ("sales_channel", "sales_channels", reservation.sales_channel_id),
            (
                "supplier_car_product",
                "supplier_car_products",
                reservation.supplier_car_product_id,
            ),
        ]
        for label, table, entity_id in checks:
            if entity_id is None:
                continue
            if not await self._exists(table, entity_id):
                missing.append(label)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing references: {', '.join(missing)}",
            )

    async def get_by_code(self, reservation_code: str) -> ReservationInput | None:
        stmt = (
            select(reservations)
            .where(reservations.c.reservation_code == reservation_code)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        row = result.mappings().first()
        if not row:
            return None
        return ReservationInput(
            reservation_id=row["id"],
            reservation_code=row["reservation_code"],
            supplier_id=row["supplier_id"],
            country_code=row.get("country_code") or "",
            pickup_office_id=row["pickup_office_id"],
            dropoff_office_id=row["dropoff_office_id"],
            pickup_office_code=row.get("pickup_office_code"),
            dropoff_office_code=row.get("dropoff_office_code"),
            car_category_id=row["car_category_id"],
            supplier_car_product_id=row["supplier_car_product_id"],
            acriss_code=row["acriss_code"],
            pickup_datetime=row["pickup_datetime"].isoformat(),
            dropoff_datetime=row["dropoff_datetime"].isoformat(),
            rental_days=row["rental_days"],
            currency_code=row["currency_code"],
            public_price_total=row["public_price_total"],
            supplier_cost_total=row["supplier_cost_total"],
            taxes_total=row["taxes_total"],
            fees_total=row["fees_total"],
            discount_total=row["discount_total"],
            commission_total=row["commission_total"],
            cashback_earned_amount=row["cashback_earned_amount"],
            booking_device=row["booking_device"],
            sales_channel_id=row["sales_channel_id"],
            traffic_source_id=row["traffic_source_id"],
            marketing_campaign_id=row["marketing_campaign_id"],
            affiliate_id=row["affiliate_id"],
            utm_source=row["utm_source"],
            utm_medium=row["utm_medium"],
            utm_campaign=row["utm_campaign"],
            utm_term=row["utm_term"],
            utm_content=row["utm_content"],
            customer_ip=row["customer_ip"],
            customer_user_agent=row["customer_user_agent"],
            status=row["status"],
            payment_status=row["payment_status"],
            supplier_reservation_code=row["supplier_reservation_code"],
            supplier_confirmed_at=row["supplier_confirmed_at"].isoformat()
            if row["supplier_confirmed_at"]
            else None,
            lock_version=row.get("lock_version", 0),
        )

    async def create_reservation(
        self,
        reservation: ReservationInput,
        contacts: Sequence[ContactInput],
        drivers: Sequence[DriverInput],
    ) -> None:
        await self._validate_references(reservation)
        res_values = asdict(reservation)
        res_values.pop("reservation_id", None)
        res_values.pop("supplier_reservation_code", None)
        res_values.pop("supplier_confirmed_at", None)
        stmt = insert(reservations).values(res_values)
        result = await self._session.execute(stmt)
        reservation_id = result.inserted_primary_key[0]

        if contacts:
            contact_rows = [
                {
                    "reservation_id": reservation_id,
                    "reservation_code": reservation.reservation_code,
                    "contact_type": c.contact_type,
                    "full_name": c.full_name,
                    "email": c.email,
                    "phone": c.phone,
                }
                for c in contacts
            ]
            await self._session.execute(insert(reservation_contacts), contact_rows)

        if drivers:
            driver_rows = [
                {
                    "reservation_id": reservation_id,
                    "reservation_code": reservation.reservation_code,
                    "is_primary_driver": 1 if d.is_primary_driver else 0,
                    "first_name": d.first_name,
                    "last_name": d.last_name,
                    "email": d.email,
                    "phone": d.phone,
                    "date_of_birth": d.date_of_birth,
                    "driver_license_number": d.driver_license_number,
                }
                for d in drivers
            ]
            await self._session.execute(insert(reservation_drivers), driver_rows)

    async def update_payment_status(
        self,
        reservation_code: str,
        payment_status: str,
        expected_lock_version: int | None = None,
    ) -> None:
        where_clause = [reservations.c.reservation_code == reservation_code]
        if expected_lock_version is not None:
            where_clause.append(reservations.c.lock_version == expected_lock_version)
        stmt = (
            update(reservations)
            .where(*where_clause)
            .values(
                payment_status=payment_status,
                lock_version=reservations.c.lock_version + 1,
            )
        )
        await self._session.execute(stmt)

    async def mark_confirmed(
        self,
        reservation_code: str,
        supplier_reservation_code: str,
        supplier_confirmed_at: str,
        expected_lock_version: int | None = None,
    ) -> None:
        where_clause = [reservations.c.reservation_code == reservation_code]
        if expected_lock_version is not None:
            where_clause.append(reservations.c.lock_version == expected_lock_version)
        stmt = (
            update(reservations)
            .where(*where_clause)
            .values(
                status="CONFIRMED",
                supplier_reservation_code=supplier_reservation_code,
                supplier_confirmed_at=datetime.fromisoformat(supplier_confirmed_at)
                if supplier_confirmed_at
                else datetime.utcnow(),
                lock_version=reservations.c.lock_version + 1,
            )
        )
        await self._session.execute(stmt)
