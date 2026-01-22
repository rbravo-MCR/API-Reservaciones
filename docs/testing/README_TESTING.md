# Guía de Testing - API Reservaciones

**Última actualización**: 2026-01-21
**Propósito**: Instrucciones completas para ejecutar tests y validaciones

---

## 📋 Tabla de Contenidos

1. [Configuración Inicial](#configuración-inicial)
2. [Tests de Integración](#tests-de-integración)
3. [Scripts de Validación SQL](#scripts-de-validación-sql)
4. [Tests por Problema Resuelto](#tests-por-problema-resuelto)
5. [Troubleshooting](#troubleshooting)

---

## 🔧 Configuración Inicial

### 1. Instalar Dependencias

```bash
# Instalar dependencias de desarrollo
pip install -e ".[dev]"

# O si usas poetry/hatch
hatch shell
pip install pytest pytest-asyncio httpx
```

### 2. Configurar Variables de Entorno

Crear archivo `.env.test` (opcional para tests con BD real):

```bash
# Para tests con base de datos real
TEST_USE_REAL_DB=true
TEST_DATABASE_URL=mysql+aiomysql://user:password@host:3306/test_database

# Para tests con SQLite in-memory (default)
TEST_USE_REAL_DB=false
```

### 3. Verificar Instalación

```bash
# Verificar que pytest encuentra los tests
pytest --collect-only

# Debería mostrar:
# tests/integration/test_prob_001_rollback.py
# tests/integration/test_prob_003_dlq.py
# tests/integration/test_prob_006_health_checks.py
# tests/integration/test_prob_007_deadlock_retry.py
# ... y más
```

---

## 🧪 Tests de Integración

### Ejecutar Todos los Tests

```bash
# Tests rápidos (SQLite in-memory)
pytest tests/integration/

# Tests con base de datos real (más lentos pero completos)
TEST_USE_REAL_DB=true pytest tests/integration/
```

### Ejecutar Tests por Categoría

```bash
# Solo tests de PROB-001 (Rollback Fix)
pytest tests/integration/test_prob_001_rollback.py -v

# Solo tests de PROB-003 (Dead Letter Queue)
pytest tests/integration/test_prob_003_dlq.py -v

# Solo tests de PROB-006 (Health Checks)
pytest tests/integration/test_prob_006_health_checks.py -v

# Solo tests de PROB-007 (Deadlock Retry)
pytest tests/integration/test_prob_007_deadlock_retry.py -v
```

### Ejecutar Tests por Marker

```bash
# Solo tests de integración
pytest -m integration

# Solo tests lentos
pytest -m slow

# Solo tests de deadlock
pytest -m deadlock

# Solo tests de DLQ
pytest -m dlq

# Excluir tests lentos
pytest -m "not slow"
```

### Tests con Salida Detallada

```bash
# Verbose output
pytest tests/integration/ -v

# Extra verbose con logs
pytest tests/integration/ -vv --log-cli-level=INFO

# Mostrar print statements
pytest tests/integration/ -s

# Detener en primer fallo
pytest tests/integration/ -x

# Ejecutar solo tests que fallaron la última vez
pytest --lf

# Modo debug (detiene en primer fallo y abre debugger)
pytest tests/integration/ --pdb
```

### Coverage de Tests

```bash
# Instalar coverage
pip install pytest-cov

# Ejecutar con coverage
pytest tests/integration/ --cov=app --cov-report=html

# Ver reporte en browser
open htmlcov/index.html  # Linux/Mac
start htmlcov/index.html  # Windows
```

---

## 🗄️ Scripts de Validación SQL

Los scripts SQL validan el estado de la base de datos directamente.

### Ubicación

```
scripts/sql/
├── 01_validate_schema.sql          # Validar estructura de tablas
├── 02_validate_data_integrity.sql  # Validar consistencia de datos
├── 03_test_deadlock_scenario.sql   # Simular deadlocks
└── 04_cleanup_test_data.sql        # Limpiar datos de prueba
```

### 1. Validar Esquema de Base de Datos

```bash
# Conectar a MySQL y ejecutar
mysql -h car-rental-outlet.cqno6yuaulrd.us-east-1.rds.amazonaws.com \
      -u admin \
      -p \
      cro_database \
      < scripts/sql/01_validate_schema.sql

# Salida esperada:
# ✓ EXISTS - Todas las tablas requeridas
# ✓ EXISTS (Optimistic Locking) - lock_version
# ✓ EXISTS (PROB-003) - outbox_dead_letters
```

**Qué verifica:**
- ✅ 13 tablas requeridas existen
- ✅ Columnas críticas (lock_version, locked_by, etc.)
- ✅ Índices únicos (idempotency_keys)
- ✅ Tabla DLQ (outbox_dead_letters)

### 2. Validar Integridad de Datos

```bash
mysql -h <host> -u <user> -p <database> < scripts/sql/02_validate_data_integrity.sql

# Salida esperada:
# ✓ N suppliers configurados
# ✓ No hay códigos duplicados
# ✓ Consistencia payment_status OK
# ℹ X eventos esperando procesamiento
```

**Qué verifica:**
- ✅ Datos maestros (suppliers, offices, categories)
- ✅ Consistencia de reservaciones
- ✅ Integridad de pagos
- ✅ Idempotency keys sin duplicados
- ✅ Estado de outbox events
- ✅ Eventos en DLQ
- ✅ Tasa de éxito de supplier requests

### 3. Probar Escenarios de Deadlock

⚠️ **ADVERTENCIA**: Solo ejecutar en desarrollo/staging

```bash
# Abrir DOS sesiones de MySQL
# Terminal 1:
mysql -h <host> -u <user> -p <database>

# Terminal 2:
mysql -h <host> -u <user> -p <database>

# Seguir instrucciones en 03_test_deadlock_scenario.sql
```

**Qué hace:**
- Simula deadlock simple con 2 reservaciones
- Simula deadlock en outbox events
- Muestra configuración de MySQL para deadlocks
- Verifica que se produce error 1213

**Propósito**: Verificar que la aplicación maneja deadlocks correctamente con retry automático (PROB-007).

### 4. Limpiar Datos de Prueba

⚠️ **ADVERTENCIA**: NUNCA ejecutar en producción

```bash
# Verificar que NO es producción primero
mysql -h <host> -u <user> -p <database> < scripts/sql/04_cleanup_test_data.sql

# Elimina:
# - Reservaciones con código TEST_*
# - Datos con emails @example.com
# - Eventos outbox completados > 7 días
# - Idempotency keys antiguas
```

---

## 📊 Tests por Problema Resuelto

### PROB-001: Rollback Manual ✅

**Archivo**: `tests/integration/test_prob_001_rollback.py`

```bash
pytest tests/integration/test_prob_001_rollback.py -v
```

**Tests incluidos:**
- ✅ Idempotencia sin double rollback
- ✅ Detección de conflictos
- ✅ Requests concurrentes idempotentes
- ✅ Rollback automático en errores

**Ejemplo de output:**
```
test_prob_001_rollback.py::TestPROB001RollbackFix::test_idempotent_request_no_double_rollback PASSED
test_prob_001_rollback.py::TestPROB001RollbackFix::test_idempotent_conflict_detection PASSED
```

### PROB-003: Dead Letter Queue ✅

**Archivo**: `tests/integration/test_prob_003_dlq.py`

```bash
pytest tests/integration/test_prob_003_dlq.py -v
```

**Tests incluidos:**
- ✅ Estructura de tabla DLQ
- ✅ Interface move_to_dlq existe
- ✅ ProcessOutbox usa DLQ en max attempts
- ✅ Logging CRITICAL
- ✅ Preservación de datos del evento

**Verificar DLQ en BD real:**
```sql
SELECT COUNT(*) FROM outbox_dead_letters;
SELECT error_code, COUNT(*) FROM outbox_dead_letters GROUP BY error_code;
```

### PROB-006: Health Checks ✅

**Archivo**: `tests/integration/test_prob_006_health_checks.py`

```bash
pytest tests/integration/test_prob_006_health_checks.py -v
```

**Tests incluidos:**
- ✅ /health - Health check básico
- ✅ /health/live - Liveness probe K8s
- ✅ /health/db - Database health
- ✅ /health/ready - Readiness probe K8s
- ✅ Tiempo de respuesta < 1s
- ✅ Estructura JSON consistente

**Probar manualmente:**
```bash
# Con la app corriendo
curl http://localhost:8000/health
curl http://localhost:8000/health/live
curl http://localhost:8000/health/db
curl http://localhost:8000/health/ready
```

### PROB-007: Deadlock Retry ✅

**Archivo**: `tests/integration/test_prob_007_deadlock_retry.py`

```bash
pytest tests/integration/test_prob_007_deadlock_retry.py -v
```

**Tests incluidos:**
- ✅ Detección de errores MySQL 1213 y 1205
- ✅ Retry con exponential backoff
- ✅ Max attempts respetado
- ✅ Errores no-deadlock no se reintentan
- ✅ Decorator @with_deadlock_retry
- ✅ Verificación de uso en endpoints

**Probar manualmente:**
```bash
# Ejecutar script de deadlock (requiere 2 terminales MySQL)
# Ver scripts/sql/03_test_deadlock_scenario.sql

# Verificar logging en la app
tail -f logs/app.log | grep "deadlock"
```

---

## 🔍 Troubleshooting

### Error: "No module named 'app'"

```bash
# Solución: Instalar proyecto en modo editable
pip install -e .
```

### Error: "pytest: command not found"

```bash
# Solución: Instalar pytest
pip install pytest pytest-asyncio
```

### Error: "Can't connect to MySQL server"

```bash
# Opción 1: Usar SQLite in-memory (default)
unset TEST_USE_REAL_DB
pytest tests/integration/

# Opción 2: Verificar credenciales de BD
cat .env.test
mysql -h <host> -u <user> -p <database> -e "SELECT 1"
```

### Tests muy lentos

```bash
# Usar SQLite in-memory en lugar de MySQL
TEST_USE_REAL_DB=false pytest tests/integration/

# Ejecutar tests en paralelo (requiere pytest-xdist)
pip install pytest-xdist
pytest tests/integration/ -n auto

# Excluir tests marcados como slow
pytest tests/integration/ -m "not slow"
```

### Error: "Deadlock detected during test"

Esto es **esperado** en `test_prob_007_deadlock_retry.py`. El test verifica que el retry funciona correctamente.

```bash
# Ver logs del test
pytest tests/integration/test_prob_007_deadlock_retry.py -v -s
```

### Error: "Circuit breaker is open"

```bash
# Los circuit breakers se resetean automáticamente entre tests
# Si persiste, verificar conftest.py fixture reset_circuit_breakers
pytest tests/integration/ --fixtures | grep circuit
```

### Limpiar base de datos de test

```bash
# Opción 1: Usar script SQL
mysql -h <host> -u <user> -p <test_database> < scripts/sql/04_cleanup_test_data.sql

# Opción 2: Drop y recrear schema
mysql -h <host> -u <user> -p -e "DROP DATABASE IF EXISTS test_database; CREATE DATABASE test_database;"
```

---

## 📈 Métricas de Cobertura Esperadas

| Componente                    | Cobertura Objetivo | Actual |
|-------------------------------|-------------------|--------|
| PROB-001: Rollback Fix        | > 90%             | TBD    |
| PROB-003: DLQ                 | > 85%             | TBD    |
| PROB-006: Health Checks       | > 95%             | TBD    |
| PROB-007: Deadlock Retry      | > 80%             | TBD    |
| app/infrastructure/db/        | > 80%             | TBD    |
| app/api/endpoints.py          | > 75%             | TBD    |

Para calcular cobertura actual:
```bash
pytest tests/integration/ --cov=app --cov-report=term-missing
```

---

## 🚀 CI/CD Integration

### GitHub Actions Example

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
          pip install pytest pytest-asyncio pytest-cov
      - name: Run tests
        run: pytest tests/integration/ --cov=app --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

---

## 📞 Soporte

Para preguntas sobre tests:
1. Revisar esta documentación
2. Revisar comentarios en archivos de test
3. Ejecutar `pytest --help` para opciones adicionales
4. Consultar [pytest docs](https://docs.pytest.org/)

**Última verificación**: 2026-01-21
**Siguiente revisión**: 2026-02-01
