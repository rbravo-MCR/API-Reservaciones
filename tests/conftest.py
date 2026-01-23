"""
Pytest configuration and shared fixtures for integration tests.

Este módulo provee fixtures reutilizables para:
- Conexión a base de datos (MySQL y SQLite in-memory)
- Cliente HTTP de prueba (FastAPI TestClient)
- Datos de prueba (reservaciones, pagos, etc.)
- Limpieza automática después de tests
"""

import asyncio

# Import metadata directly from tables module
import importlib.util
import os

# Direct imports to avoid problematic __init__.py files
import sys
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

spec = importlib.util.spec_from_file_location(
    "tables",
    "C:/proyectos/Python/API-Reservaciones/app/infrastructure/db/tables.py"
)
tables_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tables_module)
metadata = tables_module.metadata

# Try to import app
try:
    from app.api.deps import get_db_session
    from app.main import app
except ImportError as e:
    print(f"Warning: Could not import app components: {e}", file=sys.stderr)
    app = None
    get_db_session = None

# ============================================================================
# CONFIGURACIÓN DE BASE DE DATOS
# ============================================================================

# Determinar si usar base de datos real o in-memory
USE_REAL_DB = os.getenv("TEST_USE_REAL_DB", "false").lower() == "true"

if USE_REAL_DB:
    # Base de datos MySQL real (para tests de integración completos)
    TEST_DATABASE_URL = os.getenv(
        "TEST_DATABASE_URL",
        "mysql+aiomysql://admin:2gexxdfc@car-rental-outlet.cqno6yuaulrd.us-east-1.rds.amazonaws.com:3306/cro_database_test"
    )
else:
    # Base de datos SQLite in-memory (para tests rápidos)
    TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# ============================================================================
# FIXTURES DE BASE DE DATOS
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """
    Create an instance of the event loop for the entire test session.
    Necesario para tests async con pytest-asyncio.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """
    Create async engine for test database.
    Se crea una vez por sesión de tests.
    """
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,  # Cambiar a True para debug SQL
        pool_pre_ping=True,  # Verificar conexión antes de usar
    )

    # Crear todas las tablas si es in-memory
    if not USE_REAL_DB:
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

    yield engine

    # Cleanup
    if not USE_REAL_DB:
        async with engine.begin() as conn:
            await conn.run_sync(metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Create a new database session for each test.
    Auto-rollback después del test para aislamiento.
    """
    async_session = sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        # Iniciar transacción para rollback automático
        async with session.begin():
            yield session
            # Rollback automático al salir del context manager
            await session.rollback()


@pytest_asyncio.fixture
async def db_session_commit(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Database session que hace COMMIT (para tests que requieren persistencia).
    Útil para tests de integración que verifican datos después de commit.
    """
    async_session = sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        # Commit manual en el test si es necesario
        # Limpiar datos de test al final
        if USE_REAL_DB:
            await cleanup_test_data(session)
            await session.commit()


async def cleanup_test_data(session: AsyncSession):
    """
    Limpia datos de prueba después de tests con commit.
    Solo elimina datos marcados como test.
    """
    await session.execute(
        text("DELETE FROM reservations WHERE reservation_code LIKE 'TEST_%'")
    )
    await session.execute(
        text("DELETE FROM payments WHERE reservation_code LIKE 'TEST_%'")
    )
    await session.execute(
        text("DELETE FROM outbox_events WHERE aggregate_code LIKE 'TEST_%'")
    )
    await session.execute(
        text("DELETE FROM idempotency_keys WHERE idem_key LIKE 'test_%'")
    )


# ============================================================================
# FIXTURES DE CLIENTE HTTP
# ============================================================================

@pytest.fixture
def client(db_session: AsyncSession) -> Generator[TestClient, None, None]:
    """
    FastAPI TestClient con override de DB session.
    Usa la sesión de test en lugar de la producción.
    """
    def override_get_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db_session

    with TestClient(app) as test_client:
        yield test_client

    # Limpiar overrides
    app.dependency_overrides.clear()


@pytest.fixture
def client_real_db(db_session_commit: AsyncSession) -> Generator[TestClient, None, None]:
    """
    TestClient con sesión que hace commit real.
    Para tests de integración end-to-end.
    """
    def override_get_db_session():
        yield db_session_commit

    app.dependency_overrides[get_db_session] = override_get_db_session

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


# ============================================================================
# FIXTURES DE DATOS DE PRUEBA
# ============================================================================

@pytest.fixture
def sample_reservation_payload():
    """
    Payload de ejemplo para crear una reservación.
    Reutilizable en múltiples tests.
    """
    return {
        "supplier_id": 11,
        "country_code": "MX",
        "pickup_office_id": 101,
        "dropoff_office_id": 102,
        "car_category_id": 5,
        "supplier_car_product_id": 901,
        "acriss_code": "ECMN",
        "pickup_datetime": "2026-02-01T10:00:00",
        "dropoff_datetime": "2026-02-05T10:00:00",
        "rental_days": 4,
        "currency_code": "USD",
        "public_price_total": "350.00",
        "supplier_cost_total": "200.00",
        "taxes_total": "50.00",
        "fees_total": "20.00",
        "discount_total": "0.00",
        "commission_total": "30.00",
        "cashback_earned_amount": "0.00",
        "booking_device": "MOBILE_WEB",
        "sales_channel_id": 2,
        "traffic_source_id": 4,
        "marketing_campaign_id": 3,
        "affiliate_id": 7,
        "utm_source": "pytest",
        "utm_medium": "test",
        "utm_campaign": "integration",
        "customer_ip": "203.0.113.10",
        "customer_user_agent": "pytest-integration-test",
        "contacts": [
            {
                "contact_type": "BOOKER",
                "full_name": "Test User",
                "email": "test@example.com",
                "phone": "+15551234567",
            }
        ],
        "drivers": [
            {
                "is_primary_driver": True,
                "first_name": "Test",
                "last_name": "Driver",
                "email": "driver@example.com",
                "phone": "+15551234567",
            }
        ],
    }


@pytest.fixture
def unique_idem_key():
    """
    Generador de idempotency keys únicas para cada test.
    """
    import uuid
    return f"test_{uuid.uuid4().hex[:16]}"


# ============================================================================
# FIXTURES PARA TESTS DE RESILIENCIA (PROB-001 a PROB-007)
# ============================================================================

@pytest.fixture
def mock_stripe_webhook_payload():
    """
    Payload de ejemplo de webhook de Stripe para tests.
    """
    return {
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": "pi_test_123456",
                "amount": 35000,
                "currency": "usd",
                "status": "succeeded",
                "metadata": {
                    "reservation_code": "TEST_RESERVATION_001"
                }
            }
        }
    }


@pytest.fixture
def mock_stripe_signature():
    """
    Firma de Stripe simulada para tests de webhook.
    Nota: Para tests reales necesitas configurar STRIPE_WEBHOOK_SECRET.
    """
    return "t=1234567890,v1=mock_signature_for_testing"


# ============================================================================
# MARKERS DE PYTEST
# ============================================================================

def pytest_configure(config):
    """
    Configurar markers personalizados de pytest.
    """
    config.addinivalue_line(
        "markers",
        "integration: Tests de integración que requieren BD real (usa --integration)"
    )
    config.addinivalue_line(
        "markers",
        "slow: Tests lentos que pueden tomar varios segundos"
    )
    config.addinivalue_line(
        "markers",
        "deadlock: Tests de escenarios de deadlock (PROB-007)"
    )
    config.addinivalue_line(
        "markers",
        "circuit_breaker: Tests del circuit breaker (PROB-002)"
    )
    config.addinivalue_line(
        "markers",
        "dlq: Tests de Dead Letter Queue (PROB-003)"
    )


# ============================================================================
# HOOKS DE PYTEST
# ============================================================================

@pytest.fixture(autouse=True)
def reset_circuit_breakers():
    """
    Reset circuit breakers antes de cada test.
    Evita que tests fallen por breakers abiertos de tests anteriores.
    """
    from app.infrastructure.circuit_breaker import stripe_breaker, supplier_breaker

    # Reset breakers
    stripe_breaker.close()
    supplier_breaker.close()

    yield

    # Cleanup después del test
    stripe_breaker.close()
    supplier_breaker.close()
