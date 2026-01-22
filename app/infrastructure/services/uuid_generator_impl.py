"""Implementación real del generador de UUIDs."""

import secrets
import string
import uuid

from app.application.interfaces.uuid_generator import UUIDGenerator


class UUIDGeneratorImpl(UUIDGenerator):
    """
    Implementación real del UUIDGenerator.

    Genera identificadores únicos criptográficamente seguros.
    Para testing, usar FakeUUIDGenerator de application.interfaces.uuid_generator.
    """

    RESERVATION_CODE_LENGTH = 8
    ALLOWED_CHARS = string.ascii_uppercase + string.digits

    def generate_uuid(self) -> str:
        """Genera un UUID v4 aleatorio."""
        return str(uuid.uuid4())

    def generate_reservation_code(self) -> str:
        """
        Genera un código de reservación único.

        Formato: 8 caracteres alfanuméricos en mayúsculas.
        Ejemplo: A1B2C3D4

        Returns:
            String de 8 caracteres.
        """
        return "".join(
            secrets.choice(self.ALLOWED_CHARS)
            for _ in range(self.RESERVATION_CODE_LENGTH)
        )

    def generate_idempotency_key(self) -> str:
        """
        Genera una clave de idempotencia única.

        Returns:
            UUID v4 como string.
        """
        return str(uuid.uuid4())

    def generate_short_id(self, length: int = 12) -> str:
        """
        Genera un ID corto alfanumérico.

        Args:
            length: Longitud del ID (default: 12).

        Returns:
            String alfanumérico de la longitud especificada.
        """
        return "".join(secrets.choice(self.ALLOWED_CHARS) for _ in range(length))

    def generate_hex_token(self, nbytes: int = 16) -> str:
        """
        Genera un token hexadecimal seguro.

        Args:
            nbytes: Número de bytes (default: 16, produce 32 caracteres hex).

        Returns:
            String hexadecimal.
        """
        return secrets.token_hex(nbytes)
