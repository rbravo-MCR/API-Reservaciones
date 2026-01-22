"""
Integration tests for PROB-006: Health Checks

Verifica que todos los endpoints de health check funcionan correctamente:
- /health - Health check básico
- /health/live - Liveness probe para Kubernetes
- /health/db - Health check de base de datos
- /health/ready - Readiness probe completo
"""

import pytest
from fastapi.testclient import TestClient


class TestPROB006HealthChecks:
    """Tests para verificar que PROB-006 está resuelto"""

    def test_basic_health_endpoint(self, client: TestClient):
        """
        PROB-006: Verificar endpoint /health básico.

        Debe retornar 200 OK sin dependencias externas.
        """
        response = client.get("/health")
        assert response.status_code == 200, f"/health falló: {response.json()}"

        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"

    def test_liveness_probe(self, client: TestClient):
        """
        PROB-006: Verificar liveness probe para Kubernetes.

        Kubernetes usa este endpoint para saber si debe reiniciar el pod.
        Debe responder rápido sin dependencias externas.
        """
        response = client.get("/health/live")
        assert response.status_code == 200, f"Liveness probe falló: {response.json()}"

        data = response.json()
        assert data["status"] == "alive"

    def test_database_health_check(self, client: TestClient):
        """
        PROB-006: Verificar health check de base de datos.

        Debe ejecutar SELECT 1 y retornar estado de la conexión.
        """
        response = client.get("/health/db")

        # Puede ser 200 (healthy) o 503 (unhealthy) dependiendo de la BD
        assert response.status_code in [200, 503], f"DB health check status inesperado: {response.status_code}"

        data = response.json()
        assert "status" in data
        assert "checks" in data
        assert "database" in data["checks"]

        if response.status_code == 200:
            assert data["status"] == "healthy"
            assert data["checks"]["database"] == "healthy"
        else:
            assert data["status"] == "unhealthy"

    def test_readiness_probe(self, client: TestClient):
        """
        PROB-006: Verificar readiness probe completo.

        Kubernetes usa este endpoint para saber si el pod puede recibir tráfico.
        Debe verificar todas las dependencias críticas.
        """
        response = client.get("/health/ready")

        # Puede ser 200 (ready) o 503 (not ready)
        assert response.status_code in [200, 503], f"Readiness probe status inesperado: {response.status_code}"

        data = response.json()
        assert "status" in data
        assert "checks" in data

        # Debe incluir check de base de datos
        assert "database" in data["checks"]

        if response.status_code == 200:
            assert data["status"] == "ready"
        else:
            assert data["status"] == "not_ready"

    def test_health_endpoints_response_time(self, client: TestClient):
        """
        PROB-006: Verificar que health checks responden rápido.

        Los health checks deben ser rápidos para no causar timeouts en K8s.
        Objetivo: < 1 segundo
        """
        import time

        endpoints = ["/health", "/health/live", "/health/db", "/health/ready"]

        for endpoint in endpoints:
            start = time.time()
            response = client.get(endpoint)
            duration = time.time() - start

            assert duration < 1.0, f"{endpoint} tardó {duration:.2f}s (debe ser < 1s)"
            assert response.status_code in [200, 503], f"{endpoint} retornó status inesperado"

    def test_health_endpoints_structure(self, client: TestClient):
        """
        PROB-006: Verificar estructura consistente de respuestas.

        Todos los health checks deben tener estructura JSON consistente.
        """
        # Health básico
        health = client.get("/health").json()
        assert "status" in health

        # Liveness
        live = client.get("/health/live").json()
        assert "status" in live
        assert live["status"] == "alive"

        # DB health y Readiness deben tener 'checks'
        db_health = client.get("/health/db").json()
        assert "status" in db_health
        assert "checks" in db_health

        readiness = client.get("/health/ready").json()
        assert "status" in readiness
        assert "checks" in readiness


@pytest.mark.integration
class TestPROB006K8sIntegration:
    """Tests de integración simulando comportamiento de Kubernetes"""

    def test_k8s_liveness_scenario(self, client: TestClient):
        """
        PROB-006: Simular comportamiento de liveness probe de K8s.

        K8s llama /health/live cada N segundos. Si falla varias veces,
        reinicia el pod.
        """
        # Simular 3 llamadas consecutivas (como haría K8s)
        for i in range(3):
            response = client.get("/health/live")
            assert response.status_code == 200, \
                f"Liveness probe {i+1}/3 falló - K8s reiniciaría el pod"

    def test_k8s_readiness_scenario(self, client: TestClient):
        """
        PROB-006: Simular comportamiento de readiness probe de K8s.

        K8s llama /health/ready antes de enviar tráfico al pod.
        Si falla, no envía tráfico hasta que se recupere.
        """
        response = client.get("/health/ready")

        # Si está ready, debe aceptar tráfico
        if response.status_code == 200:
            # Verificar que podemos hacer requests reales
            health_response = client.get("/health")
            assert health_response.status_code == 200

        # Si no está ready, K8s no enviaría tráfico
        elif response.status_code == 503:
            data = response.json()
            # Debe indicar qué dependencia está fallando
            assert "checks" in data
            # En este caso, probablemente es la BD
            if "database" in data["checks"]:
                assert data["checks"]["database"] in ["unhealthy", "unreachable"]

    def test_health_checks_no_side_effects(self, client: TestClient):
        """
        PROB-006: Verificar que health checks no causan efectos secundarios.

        Los health checks deben ser read-only y no modificar estado.
        Pueden llamarse miles de veces por día.
        """
        # Llamar endpoints muchas veces
        for _ in range(10):
            client.get("/health")
            client.get("/health/live")
            client.get("/health/db")
            client.get("/health/ready")

        # Verificar que la aplicación sigue funcionando
        final_health = client.get("/health")
        assert final_health.status_code == 200

    @pytest.mark.asyncio
    async def test_verify_health_router_registered(self):
        """
        PROB-006: Verificar que el router de health está registrado en main.py.
        """
        from pathlib import Path

        main_file = Path("app/main.py")
        if not main_file.exists():
            pytest.skip("main.py not found")

        content = main_file.read_text()

        # Verificar import del router
        assert "from app.api.routers.health import router" in content or \
               "health_router" in content, \
               "Health router no está importado en main.py"

        # Verificar que está incluido en la app
        assert "include_router" in content and "health" in content.lower(), \
               "Health router no está registrado en main.py"
