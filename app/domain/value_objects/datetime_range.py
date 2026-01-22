"""Value Object DatetimeRange - rango de fechas para pickup/dropoff."""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class DatetimeRange:
    """
    Value Object inmutable que representa un rango de fechas/horas.

    Usado para pickup_datetime y dropoff_datetime de una reservación.

    Attributes:
        start: Fecha/hora de inicio (pickup).
        end: Fecha/hora de fin (dropoff).
    """

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start >= self.end:
            raise ValueError(
                f"start debe ser anterior a end: {self.start} >= {self.end}"
            )

    @property
    def duration(self) -> timedelta:
        """Retorna la duración del rango."""
        return self.end - self.start

    @property
    def rental_days(self) -> int:
        """
        Calcula los días de renta.

        Regla de negocio: cualquier fracción de día cuenta como día completo.
        Ejemplo: 25 horas = 2 días.
        """
        total_hours = self.duration.total_seconds() / 3600
        days = int(total_hours // 24)
        if total_hours % 24 > 0:
            days += 1
        return max(1, days)

    def overlaps_with(self, other: "DatetimeRange") -> bool:
        """Verifica si este rango se superpone con otro."""
        return self.start < other.end and other.start < self.end

    def contains(self, dt: datetime) -> bool:
        """Verifica si una fecha está dentro del rango."""
        return self.start <= dt <= self.end

    def __str__(self) -> str:
        return f"{self.start.isoformat()} -> {self.end.isoformat()}"

    @classmethod
    def from_datetimes(cls, pickup: datetime, dropoff: datetime) -> "DatetimeRange":
        """Factory method para crear desde pickup y dropoff."""
        return cls(start=pickup, end=dropoff)
