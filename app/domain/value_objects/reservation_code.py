"""Value Object ReservationCode - código único de reservación."""

import secrets
import string
from dataclasses import dataclass


@dataclass(frozen=True)
class ReservationCode:
    """
    Value Object inmutable que representa el código único de una reservación.

    Formato: 8 caracteres alfanuméricos en mayúsculas (ej: A1B2C3D4).
    """

    value: str

    CODE_LENGTH = 8
    ALLOWED_CHARS = string.ascii_uppercase + string.digits

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("reservation_code no puede estar vacío")

        if len(self.value) > 50:
            raise ValueError(f"reservation_code excede 50 caracteres: {len(self.value)}")

    def __str__(self) -> str:
        return self.value

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ReservationCode):
            return self.value == other.value
        if isinstance(other, str):
            return self.value == other
        return False

    def __hash__(self) -> int:
        return hash(self.value)

    @classmethod
    def generate(cls) -> "ReservationCode":
        """Genera un nuevo código de reservación aleatorio de 8 caracteres."""
        code = "".join(secrets.choice(cls.ALLOWED_CHARS) for _ in range(cls.CODE_LENGTH))
        return cls(value=code)

    @classmethod
    def from_string(cls, value: str) -> "ReservationCode":
        """Crea un ReservationCode desde un string existente."""
        return cls(value=value.upper().strip())
