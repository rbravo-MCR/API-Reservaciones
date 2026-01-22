"""Implementación real del servicio de reloj."""

from datetime import datetime, timezone

from app.application.interfaces.clock import Clock


class ClockImpl(Clock):
    """
    Implementación real del Clock que usa el reloj del sistema.

    Esta clase proporciona acceso al tiempo real del sistema.
    Para testing, usar FakeClock de application.interfaces.clock.
    """

    def now(self) -> datetime:
        """Retorna la fecha/hora actual con timezone UTC."""
        return datetime.now(timezone.utc)

    def now_utc(self) -> datetime:
        """Retorna la fecha/hora actual en UTC."""
        return datetime.now(timezone.utc)

    def today(self) -> datetime:
        """Retorna la fecha actual (sin hora) en UTC."""
        now = datetime.now(timezone.utc)
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    def now_naive(self) -> datetime:
        """Retorna datetime.utcnow() sin timezone (para compatibilidad)."""
        return datetime.utcnow()

    def timestamp(self) -> float:
        """Retorna el timestamp Unix actual."""
        return datetime.now(timezone.utc).timestamp()

    def iso_now(self) -> str:
        """Retorna la fecha/hora actual en formato ISO 8601."""
        return datetime.now(timezone.utc).isoformat()
