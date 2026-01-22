"""Interface Clock - Puerto para abstracción de tiempo."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone


class Clock(ABC):
    """
    Puerto para abstracción del tiempo del sistema.

    Permite inyectar implementaciones fake para testing determinista.
    """

    @abstractmethod
    def now(self) -> datetime:
        """
        Retorna la fecha/hora actual.

        Returns:
            datetime con la hora actual (timezone-aware UTC).
        """
        raise NotImplementedError

    @abstractmethod
    def now_utc(self) -> datetime:
        """
        Retorna la fecha/hora actual en UTC.

        Returns:
            datetime en UTC.
        """
        raise NotImplementedError

    @abstractmethod
    def today(self) -> datetime:
        """
        Retorna la fecha actual (sin hora).

        Returns:
            datetime con hora en 00:00:00.
        """
        raise NotImplementedError


class SystemClock(Clock):
    """Implementación real que usa el reloj del sistema."""

    def now(self) -> datetime:
        """Retorna datetime.now() con timezone UTC."""
        return datetime.now(timezone.utc)

    def now_utc(self) -> datetime:
        """Retorna datetime.utcnow() con tzinfo."""
        return datetime.now(timezone.utc)

    def today(self) -> datetime:
        """Retorna la fecha de hoy a las 00:00:00 UTC."""
        now = datetime.now(timezone.utc)
        return now.replace(hour=0, minute=0, second=0, microsecond=0)


class FakeClock(Clock):
    """
    Implementación fake para testing.

    Permite fijar el tiempo para pruebas deterministas.
    """

    def __init__(self, fixed_time: datetime | None = None):
        """
        Inicializa el clock con un tiempo fijo opcional.

        Args:
            fixed_time: Tiempo fijo a retornar. Si es None, usa el tiempo real inicial.
        """
        self._fixed_time = fixed_time or datetime.now(timezone.utc)

    def now(self) -> datetime:
        """Retorna el tiempo fijo configurado."""
        return self._fixed_time

    def now_utc(self) -> datetime:
        """Retorna el tiempo fijo en UTC."""
        return self._fixed_time.replace(tzinfo=timezone.utc)

    def today(self) -> datetime:
        """Retorna la fecha fija a las 00:00:00."""
        return self._fixed_time.replace(hour=0, minute=0, second=0, microsecond=0)

    def set_time(self, new_time: datetime) -> None:
        """
        Cambia el tiempo fijo.

        Args:
            new_time: Nuevo tiempo a fijar.
        """
        self._fixed_time = new_time

    def advance(self, seconds: int = 0, minutes: int = 0, hours: int = 0, days: int = 0) -> None:
        """
        Avanza el tiempo fijo.

        Args:
            seconds: Segundos a avanzar.
            minutes: Minutos a avanzar.
            hours: Horas a avanzar.
            days: Días a avanzar.
        """
        from datetime import timedelta

        delta = timedelta(seconds=seconds, minutes=minutes, hours=hours, days=days)
        self._fixed_time = self._fixed_time + delta
