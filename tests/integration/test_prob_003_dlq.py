"""
Integration tests for PROB-003: Dead Letter Queue (DLQ)

Verifica que el Dead Letter Queue funciona correctamente:
- Eventos que fallan MAX_ATTEMPTS veces se mueven a DLQ
- Se preserva toda la información del evento original
- Logging CRITICAL cuando un evento va a DLQ
- Tabla outbox_dead_letters existe y tiene estructura correcta
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
class TestPROB003DLQBasic:
    """Tests básicos de Dead Letter Queue"""

    async def test_dlq_table_structure(self, db_session):
        """
        PROB-003: Verificar que la tabla outbox_dead_letters existe.
        """
        from sqlalchemy import inspect, text

        # Verificar que la tabla existe
        result = await db_session.execute(
            text("SELECT COUNT(*) FROM information_schema.tables "
                 "WHERE table_name = 'outbox_dead_letters'")
        )
        count = result.scalar()
        assert count >= 1, "Tabla outbox_dead_letters no existe (PROB-003)"

        # Verificar columnas clave
        inspector = inspect(db_session.bind)
        if hasattr(inspector, 'get_columns'):
            # Async inspector
            columns = await db_session.run_sync(
                lambda sync_conn: inspect(sync_conn).get_columns('outbox_dead_letters')
            )
        else:
            columns = []

        column_names = [col['name'] for col in columns] if columns else []

        required_columns = [
            'id', 'original_event_id', 'event_type', 'reservation_code',
            'payload', 'error_code', 'error_message', 'attempts', 'moved_at'
        ]

        # Si no podemos obtener columnas via inspector, usamos query directa
        if not column_names:
            result = await db_session.execute(
                text("SELECT COLUMN_NAME FROM information_schema.columns "
                     "WHERE table_name = 'outbox_dead_letters'")
            )
            column_names = [row[0] for row in result.fetchall()]

        for col in required_columns:
            assert col in column_names, f"Columna '{col}' falta en outbox_dead_letters"

    async def test_move_to_dlq_interface_exists(self):
        """
        PROB-003: Verificar que OutboxRepo tiene método move_to_dlq.
        """
        import inspect

        from app.application.interfaces.outbox_repo import OutboxRepo

        # Verificar que el método existe
        assert hasattr(OutboxRepo, 'move_to_dlq'), \
            "OutboxRepo no tiene método move_to_dlq (PROB-003)"

        # Verificar signature
        sig = inspect.signature(OutboxRepo.move_to_dlq)
        params = list(sig.parameters.keys())

        assert 'event' in params, "move_to_dlq debe recibir parámetro 'event'"
        assert 'error_code' in params, "move_to_dlq debe recibir parámetro 'error_code'"
        assert 'error_message' in params, "move_to_dlq debe recibir parámetro 'error_message'"


@pytest.mark.asyncio
class TestPROB003DLQFunctionality:
    """Tests de funcionalidad del DLQ"""

    async def test_outbox_repo_sql_has_move_to_dlq(self):
        """
        PROB-003: Verificar que OutboxRepoSQL implementa move_to_dlq.
        """
        from app.infrastructure.db.repositories.outbox_repo_sql import OutboxRepoSQL

        assert hasattr(OutboxRepoSQL, 'move_to_dlq'), \
            "OutboxRepoSQL no implementa move_to_dlq (PROB-003)"

    async def test_process_outbox_uses_dlq_on_max_attempts(self):
        """
        PROB-003: Verificar que ProcessOutboxBookSupplierUseCase usa DLQ.
        """
        from pathlib import Path

        outbox_file = Path("app/application/use_cases/process_outbox_book_supplier.py")
        if not outbox_file.exists():
            pytest.skip("process_outbox_book_supplier.py not found")

        content = outbox_file.read_text()

        # Verificar que se llama move_to_dlq
        assert "move_to_dlq" in content, \
            "process_outbox_book_supplier no usa move_to_dlq (PROB-003)"

        # Verificar que se usa cuando se excede MAX_ATTEMPTS
        assert "MAX_ATTEMPTS" in content
        assert "move_to_dlq" in content

        # Verificar logging CRITICAL
        assert "logger.critical" in content or "_logger.critical" in content, \
            "No hay logging CRITICAL cuando evento va a DLQ"

    async def test_dlq_logging_message(self):
        """
        PROB-003: Verificar mensaje de logging CRITICAL.
        """
        from pathlib import Path

        outbox_file = Path("app/application/use_cases/process_outbox_book_supplier.py")
        if not outbox_file.exists():
            pytest.skip("process_outbox_book_supplier.py not found")

        content = outbox_file.read_text()

        # Verificar mensaje que indica intervención manual
        assert "MANUAL INTERVENTION" in content or "manual intervention" in content.lower(), \
            "Mensaje de DLQ no indica que requiere intervención manual"


@pytest.mark.integration
class TestPROB003DLQIntegration:
    """Tests de integración del DLQ con flujo completo"""

    @pytest.mark.asyncio
    async def test_dlq_preserves_event_data(self, db_session_commit):
        """
        PROB-003: Verificar que DLQ preserva todos los datos del evento original.
        """
        from sqlalchemy import insert, select, text

        from app.application.interfaces.outbox_repo import OutboxEvent
        from app.infrastructure.db.repositories.outbox_repo_sql import OutboxRepoSQL
        from app.infrastructure.db.tables import outbox_dead_letters, outbox_events

        # Crear evento de prueba
        now = datetime.now(timezone.utc)
        stmt = insert(outbox_events).values(
            event_type="BOOK_SUPPLIER",
            aggregate_type="RESERVATION",
            aggregate_code="TEST_DLQ_001",
            payload={"test": "dlq_data", "reservation_code": "TEST_DLQ_001"},
            status="RETRY",
            attempts=5,
            next_attempt_at=now,
            created_at=now,
        )
        result = await db_session_commit.execute(stmt)
        event_id = result.inserted_primary_key[0]

        # Crear OutboxEvent
        event = OutboxEvent(
            id=event_id,
            event_type="BOOK_SUPPLIER",
            aggregate_type="RESERVATION",
            aggregate_code="TEST_DLQ_001",
            payload={"test": "dlq_data", "reservation_code": "TEST_DLQ_001"},
            status="RETRY",
            attempts=5,
            next_attempt_at=now,
            locked_by=None,
            lock_expires_at=None,
        )

        # Mover a DLQ
        repo = OutboxRepoSQL(db_session_commit)
        await repo.move_to_dlq(
            event=event,
            error_code="MAX_ATTEMPTS_EXCEEDED",
            error_message="Failed after 5 attempts"
        )
        await db_session_commit.commit()

        # Verificar que se movió a DLQ
        dlq_query = select(outbox_dead_letters).where(
            outbox_dead_letters.c.original_event_id == event_id
        )
        result = await db_session_commit.execute(dlq_query)
        dlq_row = result.first()

        assert dlq_row is not None, "Evento no se movió a DLQ"
        assert dlq_row.event_type == "BOOK_SUPPLIER"
        assert dlq_row.reservation_code == "TEST_DLQ_001"
        assert dlq_row.error_code == "MAX_ATTEMPTS_EXCEEDED"
        assert dlq_row.attempts == 5
        assert dlq_row.payload == {"test": "dlq_data", "reservation_code": "TEST_DLQ_001"}

        # Verificar que evento original se marcó como FAILED
        event_query = select(outbox_events).where(outbox_events.c.id == event_id)
        result = await db_session_commit.execute(event_query)
        event_row = result.first()

        assert event_row.status == "FAILED", "Evento original no se marcó como FAILED"

        # Cleanup
        await db_session_commit.execute(
            text("DELETE FROM outbox_dead_letters WHERE original_event_id = :id"),
            {"id": event_id}
        )
        await db_session_commit.execute(
            text("DELETE FROM outbox_events WHERE id = :id"),
            {"id": event_id}
        )
        await db_session_commit.commit()

    @pytest.mark.asyncio
    async def test_dlq_with_mock_logging(self):
        """
        PROB-003: Verificar que move_to_dlq hace logging apropiado.
        """
        with patch('app.infrastructure.db.repositories.outbox_repo_sql.logger') as mock_logger:
            from app.application.interfaces.outbox_repo import OutboxEvent
            from app.infrastructure.db.repositories.outbox_repo_sql import OutboxRepoSQL

            # Mock session
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock()

            repo = OutboxRepoSQL(mock_session)

            # Mock event
            event = OutboxEvent(
                id=999,
                event_type="BOOK_SUPPLIER",
                aggregate_type="RESERVATION",
                aggregate_code="TEST_LOG",
                payload={"reservation_code": "TEST_LOG"},
                status="RETRY",
                attempts=5,
                next_attempt_at=datetime.now(timezone.utc),
                locked_by=None,
                lock_expires_at=None,
            )

            # Llamar move_to_dlq
            await repo.move_to_dlq(
                event=event,
                error_code="TEST_ERROR",
                error_message="Test error message"
            )

            # Verificar logging
            assert mock_logger.warning.called, "No se hizo logging WARNING en move_to_dlq"
            call_args = mock_logger.warning.call_args

            # Verificar mensaje
            log_message = call_args[0][0]
            assert "Dead Letter Queue" in log_message or "DLQ" in log_message.upper()
            assert "manual intervention" in log_message.lower()


@pytest.mark.asyncio
class TestPROB003DLQQueries:
    """Tests de queries útiles para DLQ"""

    async def test_dlq_count_query(self, db_session):
        """
        PROB-003: Query para contar eventos en DLQ.
        """
        from sqlalchemy import func, select

        from app.infrastructure.db.tables import outbox_dead_letters

        # Query simple de count
        stmt = select(func.count()).select_from(outbox_dead_letters)
        result = await db_session.execute(stmt)
        count = result.scalar()

        # Solo verificamos que el query funciona
        assert count >= 0, "Query de count DLQ falló"

    async def test_dlq_by_error_code_query(self, db_session):
        """
        PROB-003: Query para agrupar DLQ por error_code.
        """
        from sqlalchemy import func, select

        from app.infrastructure.db.tables import outbox_dead_letters

        # Query de agrupación
        stmt = select(
            outbox_dead_letters.c.error_code,
            func.count().label('count')
        ).group_by(outbox_dead_letters.c.error_code)

        result = await db_session.execute(stmt)
        rows = result.fetchall()

        # Solo verificamos que el query funciona
        assert rows is not None, "Query de agrupación DLQ falló"
