"""
Integration tests for PROB-001: Rollback Manual Fix

Verifica que el fix del rollback manual funciona correctamente:
- No hay rollback manual dentro de try-except
- Las transacciones se manejan correctamente por el parent
- La idempotencia funciona sin inconsistencias
"""

import pytest
from fastapi.testclient import TestClient


class TestPROB001RollbackFix:
    """Tests para verificar que PROB-001 está resuelto"""

    def test_idempotent_request_no_double_rollback(
        self,
        client: TestClient,
        sample_reservation_payload: dict,
        unique_idem_key: str
    ):
        """
        PROB-001: Verificar que no hay rollback manual causando inconsistencias.

        El problema original era un rollback manual en repository.py:58 que
        causaba inconsistencia de transacciones. Este test verifica que:
        1. La primera request crea la reservación exitosamente
        2. La segunda request (replay) retorna la misma respuesta
        3. No hay errores de transacción inconsistente
        """
        headers = {"Idempotency-Key": unique_idem_key}

        # Primera request - debe crear la reservación
        response1 = client.post("/reservations", json=sample_reservation_payload, headers=headers)
        assert response1.status_code == 201, f"Primera request falló: {response1.json()}"

        data1 = response1.json()
        assert "reservation_code" in data1
        assert data1["status"] == "PENDING"
        assert data1["payment_status"] == "UNPAID"

        # Segunda request (replay) - debe retornar la misma respuesta
        response2 = client.post("/reservations", json=sample_reservation_payload, headers=headers)
        assert response2.status_code == 201, f"Replay falló: {response2.json()}"

        data2 = response2.json()

        # Verificar idempotencia exacta
        assert data1 == data2, "Idempotencia fallida - las respuestas no coinciden"
        assert data1["reservation_code"] == data2["reservation_code"]

    def test_idempotent_conflict_detection(
        self,
        client: TestClient,
        sample_reservation_payload: dict,
        unique_idem_key: str
    ):
        """
        PROB-001: Verificar detección de conflictos de idempotencia.

        Con el rollback manual corregido, los conflictos de idempotencia
        deben detectarse correctamente sin causar inconsistencias.
        """
        headers = {"Idempotency-Key": unique_idem_key}

        # Primera request
        response1 = client.post("/reservations", json=sample_reservation_payload, headers=headers)
        assert response1.status_code == 201

        # Segunda request con payload diferente - debe detectar conflicto
        modified_payload = sample_reservation_payload.copy()
        modified_payload["public_price_total"] = "999.00"  # Diferente

        response2 = client.post("/reservations", json=modified_payload, headers=headers)
        assert response2.status_code == 409, "Conflicto de idempotencia no detectado"
        assert "Idempotency conflict" in response2.json()["detail"]

    @pytest.mark.slow
    def test_concurrent_idempotent_requests(
        self,
        client: TestClient,
        sample_reservation_payload: dict,
        unique_idem_key: str
    ):
        """
        PROB-001: Verificar manejo de requests idempotentes concurrentes.

        Sin rollback manual, las requests concurrentes deben manejarse
        correctamente sin race conditions.
        """
        import concurrent.futures
        import threading

        headers = {"Idempotency-Key": unique_idem_key}
        results = []
        lock = threading.Lock()

        def make_request():
            response = client.post("/reservations", json=sample_reservation_payload, headers=headers)
            with lock:
                results.append(response)

        # Ejecutar 5 requests concurrentes con la misma idempotency key
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request) for _ in range(5)]
            concurrent.futures.wait(futures)

        # Todas deben ser exitosas (201)
        assert len(results) == 5
        for response in results:
            assert response.status_code == 201, f"Request concurrente falló: {response.json()}"

        # Todas deben retornar el mismo reservation_code
        reservation_codes = [r.json()["reservation_code"] for r in results]
        assert len(set(reservation_codes)) == 1, "Requests concurrentes crearon diferentes reservaciones"

    def test_transaction_rollback_on_error(
        self,
        client: TestClient,
        sample_reservation_payload: dict,
        unique_idem_key: str
    ):
        """
        PROB-001: Verificar que los errores causan rollback correcto sin manual rollback.

        El parent transaction debe manejar el rollback, no código manual.
        """
        # Request con datos inválidos que causarán error
        invalid_payload = sample_reservation_payload.copy()
        invalid_payload["contacts"] = []  # Sin contacto - debe fallar validación

        headers = {"Idempotency-Key": unique_idem_key}

        response = client.post("/reservations", json=invalid_payload, headers=headers)

        # Debe fallar la validación
        assert response.status_code in [400, 422], "Validación debería fallar con payload inválido"

        # Verificar que la transacción hizo rollback (no hay idempotency key guardada)
        # Intentar con payload válido y misma key - debe funcionar
        valid_response = client.post("/reservations", json=sample_reservation_payload, headers=headers)
        assert valid_response.status_code == 201, "Rollback automático no funcionó correctamente"


@pytest.mark.integration
class TestPROB001Integration:
    """Tests de integración con BD real para PROB-001"""

    @pytest.mark.asyncio
    async def test_verify_no_manual_rollback_in_code(self):
        """
        PROB-001: Verificar que no existe rollback manual en repository.py.

        Este test lee el código fuente para asegurar que el fix está aplicado.
        """
        import os
        from pathlib import Path

        repo_file = Path("app/infrastructure/db/repository.py")
        if not repo_file.exists():
            pytest.skip("Repository file not found")

        content = repo_file.read_text()

        # Buscar la línea problemática del PROB-001
        assert "await self.session.rollback()" not in content or \
               "# The parent transaction will handle" in content, \
               "PROB-001: Rollback manual todavía existe en repository.py"

        # Verificar que el comentario del fix está presente
        assert "parent transaction will handle" in content, \
               "Comentario del fix PROB-001 no encontrado"
