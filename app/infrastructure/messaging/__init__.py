"""Módulo de mensajería y workers."""

from app.infrastructure.messaging.outbox_worker import OutboxWorker

__all__ = [
    "OutboxWorker",
]
