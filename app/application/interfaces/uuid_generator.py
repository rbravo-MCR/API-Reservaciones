"""Interface UUIDGenerator - Puerto para generación de identificadores únicos."""

import secrets
import string
import uuid
from abc import ABC, abstractmethod


class UUIDGenerator(ABC):
    """
    Puerto para generación de identificadores únicos.

    Permite inyectar implementaciones fake para testing determinista.
    """

    @abstractmethod
    def generate_uuid(self) -> str:
        """
        Genera un UUID v4 único.

        Returns:
            String con UUID en formato estándar (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx).
        """
        raise NotImplementedError

    @abstractmethod
    def generate_reservation_code(self) -> str:
        """
        Genera un código de reservación único.

        Returns:
            String de 8 caracteres alfanuméricos en mayúsculas.
        """
        raise NotImplementedError

    @abstractmethod
    def generate_idempotency_key(self) -> str:
        """
        Genera una clave de idempotencia única.

        Returns:
            String único para usar como idempotency key.
        """
        raise NotImplementedError


class RealUUIDGenerator(UUIDGenerator):
    """Implementación real que genera UUIDs aleatorios."""

    RESERVATION_CODE_LENGTH = 8
    ALLOWED_CHARS = string.ascii_uppercase + string.digits

    def generate_uuid(self) -> str:
        """Genera un UUID v4 aleatorio."""
        return str(uuid.uuid4())

    def generate_reservation_code(self) -> str:
        """Genera un código de 8 caracteres alfanuméricos."""
        return "".join(
            secrets.choice(self.ALLOWED_CHARS) for _ in range(self.RESERVATION_CODE_LENGTH)
        )

    def generate_idempotency_key(self) -> str:
        """Genera un UUID v4 como idempotency key."""
        return str(uuid.uuid4())


class FakeUUIDGenerator(UUIDGenerator):
    """
    Implementación fake para testing.

    Genera valores predecibles para pruebas deterministas.
    """

    def __init__(self, prefix: str = "TEST"):
        """
        Inicializa el generador fake.

        Args:
            prefix: Prefijo para los valores generados.
        """
        self._prefix = prefix
        self._uuid_counter = 0
        self._code_counter = 0
        self._idem_counter = 0

    def generate_uuid(self) -> str:
        """Genera un UUID predecible basado en contador."""
        self._uuid_counter += 1
        # Formato: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        hex_value = f"{self._uuid_counter:032x}"
        return f"{hex_value[:8]}-{hex_value[8:12]}-{hex_value[12:16]}-{hex_value[16:20]}-{hex_value[20:]}"

    def generate_reservation_code(self) -> str:
        """Genera un código de reservación predecible."""
        self._code_counter += 1
        return f"{self._prefix}{self._code_counter:04d}"[:8].upper()

    def generate_idempotency_key(self) -> str:
        """Genera una idempotency key predecible."""
        self._idem_counter += 1
        return f"idem-{self._prefix.lower()}-{self._idem_counter:06d}"

    def reset(self) -> None:
        """Reinicia todos los contadores."""
        self._uuid_counter = 0
        self._code_counter = 0
        self._idem_counter = 0

    def set_next_code(self, code: str) -> None:
        """
        Configura el próximo código a retornar.

        Args:
            code: Código específico a retornar en la próxima llamada.
        """
        self._next_code = code

    def generate_reservation_code_override(self) -> str:
        """Genera código usando override si está configurado."""
        if hasattr(self, "_next_code") and self._next_code:
            code = self._next_code
            self._next_code = None
            return code
        return self.generate_reservation_code()
