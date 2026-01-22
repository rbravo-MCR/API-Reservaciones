"""Worker para procesar eventos del Outbox Pattern."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import uuid4

from app.application.interfaces.clock import Clock
from app.application.interfaces.outbox_repo import OutboxRepo
from app.application.interfaces.supplier_gateway import SupplierGateway

logger = logging.getLogger(__name__)


class OutboxWorker:
    """
    Worker que procesa eventos del outbox de forma asíncrona.

    Implementa el patrón Transactional Outbox para garantizar
    consistencia eventual entre la base de datos y servicios externos.

    Características:
    - Polling configurable
    - Backoff exponencial en reintentos
    - Locking distribuido para evitar procesamiento duplicado
    - Graceful shutdown
    """

    def __init__(
        self,
        outbox_repo: OutboxRepo,
        supplier_gateway: SupplierGateway,
        clock: Clock,
        worker_id: str | None = None,
        poll_interval_seconds: float = 5.0,
        batch_size: int = 10,
        lock_duration_seconds: int = 300,
        max_retries: int = 5,
    ) -> None:
        """
        Inicializa el worker.

        Args:
            outbox_repo: Repositorio de eventos outbox.
            supplier_gateway: Gateway para llamadas a suppliers.
            clock: Servicio de reloj.
            worker_id: Identificador único del worker (auto-generado si no se provee).
            poll_interval_seconds: Intervalo entre polls en segundos.
            batch_size: Número máximo de eventos a procesar por ciclo.
            lock_duration_seconds: Duración del lock en segundos.
            max_retries: Número máximo de reintentos por evento.
        """
        self._outbox_repo = outbox_repo
        self._supplier_gateway = supplier_gateway
        self._clock = clock
        self._worker_id = worker_id or f"worker-{uuid4().hex[:8]}"
        self._poll_interval = poll_interval_seconds
        self._batch_size = batch_size
        self._lock_duration = lock_duration_seconds
        self._max_retries = max_retries
        self._running = False
        self._handlers: dict[str, Callable] = {}

    @property
    def worker_id(self) -> str:
        """Retorna el ID del worker."""
        return self._worker_id

    @property
    def is_running(self) -> bool:
        """Verifica si el worker está corriendo."""
        return self._running

    def register_handler(self, event_type: str, handler: Callable) -> None:
        """
        Registra un handler para un tipo de evento.

        Args:
            event_type: Tipo de evento (ej: BOOK_SUPPLIER_REQUESTED).
            handler: Función async que procesa el evento.
        """
        self._handlers[event_type] = handler
        logger.info(f"Handler registrado para evento: {event_type}")

    async def start(self) -> None:
        """Inicia el worker en modo polling."""
        self._running = True
        logger.info(f"OutboxWorker {self._worker_id} iniciado")

        while self._running:
            try:
                processed = await self._process_batch()
                if processed == 0:
                    await asyncio.sleep(self._poll_interval)
            except Exception as e:
                logger.exception(f"Error en ciclo del worker: {e}")
                await asyncio.sleep(self._poll_interval)

    async def stop(self) -> None:
        """Detiene el worker de forma graceful."""
        self._running = False
        logger.info(f"OutboxWorker {self._worker_id} detenido")

    async def process_single(self, event_id: int) -> bool:
        """
        Procesa un evento específico por ID.

        Args:
            event_id: ID del evento a procesar.

        Returns:
            True si se procesó exitosamente, False en caso contrario.
        """
        event = await self._outbox_repo.get_by_id(event_id)
        if not event:
            logger.warning(f"Evento {event_id} no encontrado")
            return False
        return await self._process_event(event)

    async def _process_batch(self) -> int:
        """
        Procesa un batch de eventos pendientes.

        Returns:
            Número de eventos procesados.
        """
        now = self._clock.now()
        events = await self._outbox_repo.claim_ready(
            limit=self._batch_size,
            locked_by=self._worker_id,
            now=now,
        )

        if not events:
            return 0

        processed = 0
        for event in events:
            try:
                success = await self._process_event(event)
                if success:
                    processed += 1
            except Exception as e:
                logger.exception(f"Error procesando evento {event.id}: {e}")

        return processed

    async def _process_event(self, event) -> bool:
        """
        Procesa un evento individual.

        Args:
            event: Evento del outbox a procesar.

        Returns:
            True si se procesó exitosamente.
        """
        event_type = event.event_type
        logger.info(
            f"Procesando evento {event.id} tipo={event_type} "
            f"aggregate={event.aggregate_type}:{event.aggregate_id}"
        )

        handler = self._handlers.get(event_type)
        if not handler:
            logger.warning(f"No hay handler para evento tipo: {event_type}")
            await self._outbox_repo.mark_done(event.id)
            return True

        try:
            await handler(event)
            await self._outbox_repo.mark_done(event.id)
            logger.info(f"Evento {event.id} procesado exitosamente")
            return True

        except Exception as e:
            logger.exception(f"Error en handler para evento {event.id}: {e}")
            await self._handle_failure(event)
            return False

    async def _handle_failure(self, event) -> None:
        """
        Maneja el fallo de un evento.

        Implementa backoff exponencial para reintentos.

        Args:
            event: Evento que falló.
        """
        attempts = event.attempts + 1

        if attempts >= self._max_retries:
            logger.error(
                f"Evento {event.id} excedió máximo de reintentos ({self._max_retries})"
            )
            await self._outbox_repo.mark_failed(event.id)
            return

        # Backoff exponencial: 30s, 60s, 120s, 240s, 480s
        backoff_seconds = 30 * (2 ** (attempts - 1))
        next_attempt = self._clock.now() + timedelta(seconds=backoff_seconds)

        logger.info(
            f"Evento {event.id} reintento {attempts}/{self._max_retries} "
            f"programado para {next_attempt.isoformat()}"
        )

        await self._outbox_repo.mark_retry(
            event_id=event.id,
            next_attempt_at=next_attempt,
            attempts=attempts,
        )


class OutboxWorkerFactory:
    """Factory para crear instancias de OutboxWorker."""

    @staticmethod
    def create(
        outbox_repo: OutboxRepo,
        supplier_gateway: SupplierGateway,
        clock: Clock,
        **kwargs,
    ) -> OutboxWorker:
        """
        Crea una instancia de OutboxWorker.

        Args:
            outbox_repo: Repositorio de outbox.
            supplier_gateway: Gateway de suppliers.
            clock: Servicio de reloj.
            **kwargs: Argumentos adicionales para el worker.

        Returns:
            Instancia configurada de OutboxWorker.
        """
        return OutboxWorker(
            outbox_repo=outbox_repo,
            supplier_gateway=supplier_gateway,
            clock=clock,
            **kwargs,
        )
