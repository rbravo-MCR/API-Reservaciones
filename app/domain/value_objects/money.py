"""Value Object Money - representa un valor monetario con su moneda."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Money:
    """
    Value Object inmutable que representa un monto monetario.

    Attributes:
        amount: Monto decimal (hasta 2 decimales).
        currency_code: Código ISO 4217 de la moneda (ej: USD, MXN, EUR).
    """

    amount: Decimal
    currency_code: str

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            object.__setattr__(self, "amount", Decimal(str(self.amount)))

        if len(self.currency_code) != 3:
            raise ValueError(f"currency_code debe ser de 3 caracteres: {self.currency_code}")

        if self.amount < 0:
            raise ValueError(f"amount no puede ser negativo: {self.amount}")

    def __add__(self, other: "Money") -> "Money":
        if not isinstance(other, Money):
            raise TypeError(f"No se puede sumar Money con {type(other)}")
        if self.currency_code != other.currency_code:
            raise ValueError(
                f"No se pueden sumar montos de diferentes monedas: "
                f"{self.currency_code} vs {other.currency_code}"
            )
        return Money(amount=self.amount + other.amount, currency_code=self.currency_code)

    def __sub__(self, other: "Money") -> "Money":
        if not isinstance(other, Money):
            raise TypeError(f"No se puede restar Money con {type(other)}")
        if self.currency_code != other.currency_code:
            raise ValueError(
                f"No se pueden restar montos de diferentes monedas: "
                f"{self.currency_code} vs {other.currency_code}"
            )
        return Money(amount=self.amount - other.amount, currency_code=self.currency_code)

    def is_zero(self) -> bool:
        return self.amount == Decimal("0")

    def __str__(self) -> str:
        return f"{self.amount:.2f} {self.currency_code}"

    @classmethod
    def zero(cls, currency_code: str = "USD") -> "Money":
        """Crea un Money con valor cero."""
        return cls(amount=Decimal("0"), currency_code=currency_code)

    @classmethod
    def from_cents(cls, cents: int, currency_code: str) -> "Money":
        """Crea un Money desde centavos (útil para Stripe)."""
        return cls(amount=Decimal(cents) / 100, currency_code=currency_code)

    def to_cents(self) -> int:
        """Convierte a centavos (útil para Stripe)."""
        return int(self.amount * 100)
