"""Excepciones de dominio para el sistema de reservaciones."""


class DomainError(Exception):
    """Clase base para todos los errores de dominio."""

    def __init__(self, message: str, code: str | None = None):
        self.message = message
        self.code = code or self.__class__.__name__
        super().__init__(self.message)


# === Errores de Reservación ===


class ReservationNotFoundError(DomainError):
    """La reservación no existe."""

    def __init__(self, reservation_code: str):
        super().__init__(
            message=f"Reservación no encontrada: {reservation_code}",
            code="RESERVATION_NOT_FOUND",
        )
        self.reservation_code = reservation_code


class ReservationAlreadyExistsError(DomainError):
    """Ya existe una reservación con ese código."""

    def __init__(self, reservation_code: str):
        super().__init__(
            message=f"Ya existe una reservación con código: {reservation_code}",
            code="RESERVATION_ALREADY_EXISTS",
        )
        self.reservation_code = reservation_code


class InvalidReservationStatusError(DomainError):
    """El estado de la reservación no permite la operación."""

    def __init__(self, current_status: str, expected_status: str | list[str], operation: str):
        expected = expected_status if isinstance(expected_status, str) else ", ".join(expected_status)
        super().__init__(
            message=f"No se puede {operation}: estado actual '{current_status}', esperado '{expected}'",
            code="INVALID_RESERVATION_STATUS",
        )
        self.current_status = current_status
        self.expected_status = expected_status
        self.operation = operation


class OptimisticLockError(DomainError):
    """Conflicto de concurrencia al actualizar la reservación."""

    def __init__(self, reservation_code: str, expected_version: int, actual_version: int):
        super().__init__(
            message=f"Conflicto de concurrencia en reservación {reservation_code}: "
            f"versión esperada {expected_version}, versión actual {actual_version}",
            code="OPTIMISTIC_LOCK_ERROR",
        )
        self.reservation_code = reservation_code
        self.expected_version = expected_version
        self.actual_version = actual_version


# === Errores de Pago ===


class PaymentNotFoundError(DomainError):
    """El pago no existe."""

    def __init__(self, payment_id: int | None = None, reservation_code: str | None = None):
        identifier = f"ID {payment_id}" if payment_id else f"reservación {reservation_code}"
        super().__init__(
            message=f"Pago no encontrado para {identifier}",
            code="PAYMENT_NOT_FOUND",
        )
        self.payment_id = payment_id
        self.reservation_code = reservation_code


class PaymentAlreadyProcessedError(DomainError):
    """El pago ya fue procesado (capturado o fallido)."""

    def __init__(self, payment_id: int, current_status: str):
        super().__init__(
            message=f"El pago {payment_id} ya fue procesado con estado: {current_status}",
            code="PAYMENT_ALREADY_PROCESSED",
        )
        self.payment_id = payment_id
        self.current_status = current_status


class DuplicatePaymentEventError(DomainError):
    """Evento de pago duplicado (idempotencia)."""

    def __init__(self, stripe_event_id: str):
        super().__init__(
            message=f"Evento de Stripe ya procesado: {stripe_event_id}",
            code="DUPLICATE_PAYMENT_EVENT",
        )
        self.stripe_event_id = stripe_event_id


# === Errores de Supplier ===


class SupplierNotFoundError(DomainError):
    """El proveedor no existe."""

    def __init__(self, supplier_id: int):
        super().__init__(
            message=f"Proveedor no encontrado: {supplier_id}",
            code="SUPPLIER_NOT_FOUND",
        )
        self.supplier_id = supplier_id


class SupplierBookingFailedError(DomainError):
    """Falló la confirmación con el proveedor."""

    def __init__(
        self,
        supplier_id: int,
        reservation_code: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ):
        super().__init__(
            message=f"Falló booking con supplier {supplier_id} para {reservation_code}: {error_message}",
            code="SUPPLIER_BOOKING_FAILED",
        )
        self.supplier_id = supplier_id
        self.reservation_code = reservation_code
        self.supplier_error_code = error_code
        self.supplier_error_message = error_message


class SupplierTimeoutError(DomainError):
    """Timeout en la comunicación con el proveedor."""

    def __init__(self, supplier_id: int, timeout_seconds: float):
        super().__init__(
            message=f"Timeout de {timeout_seconds}s en comunicación con supplier {supplier_id}",
            code="SUPPLIER_TIMEOUT",
        )
        self.supplier_id = supplier_id
        self.timeout_seconds = timeout_seconds


# === Errores de Idempotencia ===


class IdempotencyConflictError(DomainError):
    """Conflicto de idempotencia: mismo key pero diferente request."""

    def __init__(self, idem_key: str, scope: str):
        super().__init__(
            message=f"Conflicto de idempotencia: key '{idem_key}' en scope '{scope}' "
            f"ya existe con diferente request hash",
            code="IDEMPOTENCY_CONFLICT",
        )
        self.idem_key = idem_key
        self.scope = scope


# === Errores de Validación ===


class ValidationError(DomainError):
    """Error de validación de datos de entrada."""

    def __init__(self, field: str, message: str):
        super().__init__(
            message=f"Validación fallida en '{field}': {message}",
            code="VALIDATION_ERROR",
        )
        self.field = field


class InvalidDateRangeError(DomainError):
    """Rango de fechas inválido."""

    def __init__(self, message: str):
        super().__init__(message=message, code="INVALID_DATE_RANGE")


class InvalidMoneyError(DomainError):
    """Monto monetario inválido."""

    def __init__(self, message: str):
        super().__init__(message=message, code="INVALID_MONEY")


# === Errores de Recibo ===


class ReceiptNotReadyError(DomainError):
    """El recibo aún no está disponible (reservación no confirmada)."""

    def __init__(self, reservation_code: str, current_status: str):
        super().__init__(
            message=f"Recibo no disponible para {reservation_code}: estado actual '{current_status}'",
            code="RECEIPT_NOT_READY",
        )
        self.reservation_code = reservation_code
        self.current_status = current_status
