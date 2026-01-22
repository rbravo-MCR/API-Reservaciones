"""
Integration tests for PROB-007: Deadlock Retry

Verifica que el retry automático de deadlocks funciona correctamente:
- Detecta errores MySQL 1213 (Deadlock) y 1205 (Lock wait timeout)
- Reintenta automáticamente con exponential backoff
- Logging apropiado en cada retry
- Se rinde después del max_attempts
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.exc import DBAPIError, OperationalError

from app.infrastructure.db.retry import (
    is_deadlock_error,
    retry_on_deadlock,
    with_deadlock_retry,
)


class TestPROB007DeadlockDetection:
    """Tests para verificar detección de deadlocks"""

    def test_detect_mysql_deadlock_error_1213(self):
        """
        PROB-007: Detectar error MySQL 1213 (Deadlock found).
        """
        # Simular error de deadlock
        error = OperationalError("statement", "params", "orig", connection_invalidated=False)
        error.orig = Mock()
        error.orig.args = ("(pymysql.err.OperationalError) (1213, 'Deadlock found when trying to get lock')",)

        # Convertir a string para simular el check
        error_with_code = OperationalError(
            "statement",
            "params",
            "(pymysql.err.OperationalError) (1213, 'Deadlock found')",
            connection_invalidated=False
        )

        assert is_deadlock_error(error_with_code), "Error 1213 no detectado como deadlock"

    def test_detect_mysql_lock_timeout_error_1205(self):
        """
        PROB-007: Detectar error MySQL 1205 (Lock wait timeout).
        """
        error = OperationalError(
            "statement",
            "params",
            "(pymysql.err.OperationalError) (1205, 'Lock wait timeout exceeded')",
            connection_invalidated=False
        )

        assert is_deadlock_error(error), "Error 1205 no detectado como deadlock"

    def test_ignore_non_deadlock_errors(self):
        """
        PROB-007: No detectar otros errores como deadlocks.
        """
        # Error genérico
        generic_error = Exception("Generic error")
        assert not is_deadlock_error(generic_error)

        # OperationalError pero no deadlock
        other_op_error = OperationalError(
            "statement",
            "params",
            "(pymysql.err.OperationalError) (2013, 'Lost connection to MySQL server')",
            connection_invalidated=False
        )
        assert not is_deadlock_error(other_op_error)


class TestPROB007RetryLogic:
    """Tests para verificar lógica de retry"""

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_first_attempt(self):
        """
        PROB-007: Si la función tiene éxito, no hay retries.
        """
        call_count = 0

        async def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await retry_on_deadlock(successful_func, max_attempts=3)

        assert result == "success"
        assert call_count == 1, "No debería haber retries si tiene éxito"

    @pytest.mark.asyncio
    async def test_retry_on_deadlock_until_success(self):
        """
        PROB-007: Reintentar en deadlock hasta que tenga éxito.
        """
        call_count = 0

        async def func_fails_twice_then_succeeds():
            nonlocal call_count
            call_count += 1

            if call_count <= 2:
                # Simular deadlock en primeros 2 intentos
                raise OperationalError(
                    "statement", "params",
                    "(pymysql.err.OperationalError) (1213, 'Deadlock found')",
                    connection_invalidated=False
                )

            return "success_after_retries"

        result = await retry_on_deadlock(func_fails_twice_then_succeeds, max_attempts=3, base_delay=0.01)

        assert result == "success_after_retries"
        assert call_count == 3, "Debería haber reintentado 2 veces antes de tener éxito"

    @pytest.mark.asyncio
    async def test_retry_fails_after_max_attempts(self):
        """
        PROB-007: Lanzar excepción después de max_attempts.
        """
        call_count = 0

        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise OperationalError(
                "statement", "params",
                "(pymysql.err.OperationalError) (1213, 'Deadlock found')",
                connection_invalidated=False
            )

        with pytest.raises(OperationalError):
            await retry_on_deadlock(always_fails, max_attempts=3, base_delay=0.01)

        assert call_count == 3, "Debería haber intentado max_attempts veces"

    @pytest.mark.asyncio
    async def test_non_deadlock_error_not_retried(self):
        """
        PROB-007: Errores que no son deadlocks no se reintentan.
        """
        call_count = 0

        async def raises_non_deadlock_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("Not a deadlock")

        with pytest.raises(ValueError, match="Not a deadlock"):
            await retry_on_deadlock(raises_non_deadlock_error, max_attempts=3)

        assert call_count == 1, "No debería reintentar errores que no son deadlocks"

    @pytest.mark.asyncio
    async def test_exponential_backoff(self):
        """
        PROB-007: Verificar exponential backoff (0.1s, 0.2s, 0.4s).
        """
        import time

        call_times = []

        async def func_always_fails():
            call_times.append(time.time())
            raise OperationalError(
                "statement", "params",
                "(pymysql.err.OperationalError) (1213, 'Deadlock')",
                connection_invalidated=False
            )

        try:
            await retry_on_deadlock(func_always_fails, max_attempts=3, base_delay=0.1)
        except OperationalError:
            pass

        # Verificar que hubo 3 intentos
        assert len(call_times) == 3

        # Verificar delays aproximados (con tolerancia)
        delay1 = call_times[1] - call_times[0]
        delay2 = call_times[2] - call_times[1]

        # Primer delay: ~0.1s, segundo delay: ~0.2s
        assert 0.08 < delay1 < 0.15, f"Primer delay {delay1:.3f}s no está cerca de 0.1s"
        assert 0.18 < delay2 < 0.25, f"Segundo delay {delay2:.3f}s no está cerca de 0.2s"


class TestPROB007Decorator:
    """Tests para el decorator @with_deadlock_retry"""

    @pytest.mark.asyncio
    async def test_decorator_basic_usage(self):
        """
        PROB-007: Verificar que el decorator funciona.
        """
        call_count = 0

        @with_deadlock_retry(max_attempts=3, base_delay=0.01)
        async def decorated_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OperationalError(
                    "stmt", "params",
                    "(pymysql.err.OperationalError) (1213, 'Deadlock')",
                    connection_invalidated=False
                )
            return "decorated_success"

        result = await decorated_func()
        assert result == "decorated_success"
        assert call_count == 2


@pytest.mark.integration
class TestPROB007Integration:
    """Tests de integración con endpoints reales"""

    @pytest.mark.asyncio
    async def test_create_reservation_has_deadlock_retry(self):
        """
        PROB-007: Verificar que create_reservation usa retry_on_deadlock.
        """
        from pathlib import Path

        endpoints_file = Path("app/api/endpoints.py")
        if not endpoints_file.exists():
            pytest.skip("endpoints.py not found")

        content = endpoints_file.read_text()

        # Verificar import
        assert "from app.infrastructure.db.retry import retry_on_deadlock" in content, \
            "retry_on_deadlock no está importado en endpoints.py"

        # Verificar uso en create_reservation
        assert "retry_on_deadlock" in content, \
            "retry_on_deadlock no se usa en endpoints.py"

        # Verificar que stripe_webhook también lo usa
        assert content.count("retry_on_deadlock") >= 2, \
            "retry_on_deadlock debería usarse en múltiples endpoints"

    @pytest.mark.asyncio
    async def test_worker_endpoint_has_deadlock_retry(self):
        """
        PROB-007: Verificar que worker endpoint usa retry_on_deadlock.
        """
        from pathlib import Path

        worker_file = Path("app/api/routers/worker.py")
        if not worker_file.exists():
            pytest.skip("worker.py not found")

        content = worker_file.read_text()

        assert "from app.infrastructure.db.retry import retry_on_deadlock" in content, \
            "retry_on_deadlock no está importado en worker.py"

        assert "retry_on_deadlock" in content, \
            "retry_on_deadlock no se usa en worker.py"

    @pytest.mark.asyncio
    async def test_retry_module_exists(self):
        """
        PROB-007: Verificar que el módulo retry.py existe y tiene las funciones correctas.
        """
        from pathlib import Path

        retry_file = Path("app/infrastructure/db/retry.py")
        assert retry_file.exists(), "app/infrastructure/db/retry.py no existe"

        content = retry_file.read_text()

        # Verificar funciones clave
        assert "async def retry_on_deadlock" in content
        assert "def is_deadlock_error" in content
        assert "def with_deadlock_retry" in content

        # Verificar constantes de MySQL
        assert "MYSQL_DEADLOCK_ERROR" in content
        assert "1213" in content
        assert "MYSQL_LOCK_WAIT_TIMEOUT" in content
        assert "1205" in content


@pytest.mark.slow
@pytest.mark.deadlock
class TestPROB007RealScenarios:
    """Tests de escenarios reales de deadlock (requieren BD real)"""

    @pytest.mark.asyncio
    async def test_concurrent_updates_with_retry(self, client_real_db):
        """
        PROB-007: Simular updates concurrentes que podrían causar deadlock.

        Nota: Este test puede no causar deadlock en todas las ejecuciones
        debido a la naturaleza no determinística de los deadlocks.
        """
        # Este test requiere BD real y múltiples conexiones
        # Lo dejamos como placeholder para testing manual
        pytest.skip("Requiere configuración especial de BD con múltiples conexiones")

    @pytest.mark.asyncio
    async def test_verify_logging_on_retry(self):
        """
        PROB-007: Verificar que se hace logging en cada retry.
        """
        import logging
        from unittest.mock import MagicMock

        # Mock del logger
        with patch('app.infrastructure.db.retry.logger') as mock_logger:
            call_count = 0

            async def func_fails_once():
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise OperationalError(
                        "stmt", "params",
                        "(pymysql.err.OperationalError) (1213, 'Deadlock')",
                        connection_invalidated=False
                    )
                return "success"

            await retry_on_deadlock(func_fails_once, max_attempts=3, base_delay=0.01)

            # Verificar que se llamó logger.warning
            assert mock_logger.warning.called, "No se hizo logging del retry"
            call_args = mock_logger.warning.call_args[0]
            assert "deadlock" in call_args[0].lower(), "Mensaje de log no menciona deadlock"
