import enum
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.infrastructure.db.base import Base


class ReservationStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAID = "PAID"
    CONFIRMED = "CONFIRMED"
    CONFIRMED_INTERNAL = "CONFIRMED_INTERNAL"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    CANCELLED_REFUND = "CANCELLED_REFUND"


class OutboxStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class ReservationModel(Base):
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reservation_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    
    # Foreign Keys
    supplier_id: Mapped[int] = mapped_column(Integer, nullable=False)
    pickup_office_id: Mapped[int] = mapped_column(Integer, nullable=False)
    dropoff_office_id: Mapped[int] = mapped_column(Integer, nullable=False)
    car_category_id: Mapped[int] = mapped_column(Integer, nullable=False)
    sales_channel_id: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Dates
    pickup_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    dropoff_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    rental_days: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Financials
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    public_price_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    supplier_cost_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    
    # Status
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(ReservationStatus), default=ReservationStatus.DRAFT, nullable=False, index=True
    )
    payment_status: Mapped[str] = mapped_column(String(20), default="UNPAID", nullable=False)
    
    # Customer Snapshot
    customer_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Meta
    booking_device: Mapped[str] = mapped_column(String(20), default="DESKTOP", nullable=False)
    lock_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    
    # Supplier Confirmation
    supplier_reservation_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    supplier_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PaymentModel(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reservation_id: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False) # e.g. STRIPE
    provider_transaction_id: Mapped[str] = mapped_column(String(255), nullable=True)
    
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    
    __table_args__ = (
        UniqueConstraint("provider", "provider_transaction_id", name="uq_payments_provider_tx"),
    )


class OutboxEventModel(Base):
    __tablename__ = "outbox_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(32), nullable=False)
    aggregate_id: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    
    status: Mapped[OutboxStatus] = mapped_column(
        Enum(OutboxStatus), default=OutboxStatus.PENDING, nullable=False, index=True
    )
    
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Alias for compatibility
    @property
    def type(self): return self.event_type
    @type.setter
    def type(self, value): self.event_type = value

    @property
    def retry_count(self): return self.attempts
    @retry_count.setter
    def retry_count(self, value): self.attempts = value


class OutboxDeadLetterModel(Base):
    """
    Dead Letter Queue for permanently failed outbox events.

    Events that exceed MAX_ATTEMPTS are moved here for manual intervention
    and analysis. This prevents data loss and provides visibility into
    failures requiring operational attention.
    """
    __tablename__ = "outbox_dead_letters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Original event information
    original_event_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(32), nullable=False)
    aggregate_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Business context
    reservation_code: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    # Event data
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    # Failure context
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)

    # Audit
    moved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
