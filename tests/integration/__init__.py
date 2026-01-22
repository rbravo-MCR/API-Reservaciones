"""
Integration tests package.

Tests de integración que verifican el funcionamiento correcto de:
- PROB-001: Rollback manual corregido
- PROB-002: Circuit Breaker
- PROB-003: Dead Letter Queue
- PROB-004: Global Exception Handler
- PROB-005: Timeouts
- PROB-006: Health Checks
- PROB-007: Deadlock Retry

Para ejecutar solo tests de integración:
    pytest tests/integration/

Para ejecutar con base de datos real:
    TEST_USE_REAL_DB=true pytest tests/integration/
"""
