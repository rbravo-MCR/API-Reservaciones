"""Entidad SupplierRequest - representa una solicitud al proveedor."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class SupplierRequestStatus(str, Enum):
    """Estados de una solicitud al proveedor."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


class SupplierRequestType(str, Enum):
    """Tipos de solicitudes al proveedor."""

    BOOK = "BOOK"
    CANCEL = "CANCEL"
    MODIFY = "MODIFY"
    STATUS_CHECK = "STATUS_CHECK"


@dataclass
class SupplierRequest:
    """
    Entidad que registra las solicitudes enviadas a proveedores externos.

    Permite tracking de intentos, errores y respuestas para debugging y reintentos.
    """

    # Identificadores
    id: int | None = None
    reservation_id: int | None = None
    reservation_code: str | None = None
    supplier_id: int | None = None

    # Tipo y estado
    request_type: SupplierRequestType = SupplierRequestType.BOOK
    status: SupplierRequestStatus = SupplierRequestStatus.PENDING

    # Idempotencia
    idem_key: str | None = None

    # Intentos
    attempt: int = 0

    # Respuesta HTTP
    http_status: int | None = None
    error_code: str | None = None
    error_message: str | None = None

    # Payloads (JSON)
    request_payload: dict[str, Any] | None = None
    response_payload: dict[str, Any] | None = None

    # Timestamps
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # === Propiedades ===

    @property
    def is_successful(self) -> bool:
        """Verifica si la solicitud fue exitosa."""
        return self.status == SupplierRequestStatus.SUCCESS

    @property
    def is_final(self) -> bool:
        """Verifica si la solicitud está en un estado final."""
        return self.status in (
            SupplierRequestStatus.SUCCESS,
            SupplierRequestStatus.FAILED,
        )

    @property
    def can_retry(self) -> bool:
        """Verifica si la solicitud puede ser reintentada."""
        return self.status in (
            SupplierRequestStatus.PENDING,
            SupplierRequestStatus.FAILED,
            SupplierRequestStatus.TIMEOUT,
        )

    # === Métodos de negocio ===

    def start_attempt(self) -> None:
        """Inicia un nuevo intento de la solicitud."""
        self.attempt += 1
        self.status = SupplierRequestStatus.IN_PROGRESS
        self.error_code = None
        self.error_message = None

    def mark_success(self, response_payload: dict[str, Any], http_status: int = 200) -> None:
        """Marca la solicitud como exitosa."""
        self.status = SupplierRequestStatus.SUCCESS
        self.response_payload = response_payload
        self.http_status = http_status

    def mark_failed(
        self,
        error_code: str,
        error_message: str,
        http_status: int | None = None,
        response_payload: dict[str, Any] | None = None,
    ) -> None:
        """Marca la solicitud como fallida."""
        self.status = SupplierRequestStatus.FAILED
        self.error_code = error_code
        self.error_message = error_message
        self.http_status = http_status
        if response_payload:
            self.response_payload = response_payload

    def mark_timeout(self) -> None:
        """Marca la solicitud como timeout."""
        self.status = SupplierRequestStatus.TIMEOUT
        self.error_code = "TIMEOUT"
        self.error_message = "Request timed out"

    @classmethod
    def create_booking_request(
        cls,
        reservation_id: int,
        reservation_code: str,
        supplier_id: int,
        idem_key: str,
        request_payload: dict[str, Any],
    ) -> "SupplierRequest":
        """Factory para crear una solicitud de booking."""
        return cls(
            reservation_id=reservation_id,
            reservation_code=reservation_code,
            supplier_id=supplier_id,
            request_type=SupplierRequestType.BOOK,
            status=SupplierRequestStatus.PENDING,
            idem_key=idem_key,
            attempt=0,
            request_payload=request_payload,
        )
