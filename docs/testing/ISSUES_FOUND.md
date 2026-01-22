# Problemas Encontrados Durante Ejecución de Tests

**Fecha**: 2026-01-21
**Estado**: Requiere corrección antes de ejecutar tests

---

## 🔴 Problemas Críticos que Bloquean Tests

### 1. Error en CircuitBreaker - Parámetro Incorrecto

**Archivo**: `app/infrastructure/circuit_breaker.py:26-28`

**Error**:
```python
TypeError: CircuitBreaker.__init__() got an unexpected keyword argument 'timeout_duration'
```

**Causa**:
El parámetro correcto de `pybreaker.CircuitBreaker` es `reset_timeout`, no `timeout_duration`.

**Solución Aplicada**: ✅ CORREGIDO
```python
# Antes:
stripe_breaker = CircuitBreaker(
    fail_max=5,
    timeout_duration=60,  # ❌ Incorrecto
    name="stripe_circuit_breaker",
)

# Después:
stripe_breaker = CircuitBreaker(
    fail_max=5,
    reset_timeout=60,  # ✅ Correcto
    name="stripe_circuit_breaker",
)
```

---

### 2. Import Faltante en `__init__.py`

**Archivo**: `app/infrastructure/__init__.py:16`

**Error**:
```python
ImportError: cannot import name 'get_async_engine' from 'app.infrastructure.db.mysql_engine'
```

**Causa**:
El archivo `mysql_engine.py` solo exporta:
- `build_engine()`
- `build_sessionmaker()`
- `session_scope()`

Pero `__init__.py` intenta importar:
- `get_async_engine` (NO EXISTE)
- `get_async_session` (NO EXISTE)

**Solución Aplicada**: ✅ CORREGIDO
```python
# Comentado imports inexistentes en __init__.py:
# from app.infrastructure.db.mysql_engine import get_async_engine, get_async_session
```

---

### 3. Clase InMemoryStripeGateway No Existe

**Archivo**: `app/infrastructure/in_memory/__init__.py:10`

**Error**:
```python
ImportError: cannot import name 'InMemoryStripeGateway' from 'app.infrastructure.in_memory.stripe_gateway'
```

**Causa**:
Se intenta importar `InMemoryStripeGateway` pero la clase no existe en `stripe_gateway.py`.

**Solución Requerida**: ⚠️ PENDIENTE

**Opciones**:
1. Crear la clase `InMemoryStripeGateway` en `app/infrastructure/in_memory/stripe_gateway.py`
2. Comentar el import si no se usa actualmente
3. Verificar nombre correcto de la clase

```python
# Verificar en stripe_gateway.py qué clase existe realmente
# Posiblemente el nombre correcto es diferente
```

---

## 🟡 Warnings y Mejoras Sugeridas

### 4. Fixtures de Tests Dependen de Imports Problemáticos

**Archivo**: `tests/conftest.py`

**Issue**:
El conftest intenta importar desde módulos que tienen errores, causando que los tests no se puedan ejecutar.

**Solución Temporal Aplicada**: ✅ PARCIAL
```python
# Import directo de metadata usando importlib para evitar __init__.py problemático
import importlib.util
spec = importlib.util.spec_from_file_location("tables", "app/infrastructure/db/tables.py")
tables_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tables_module)
metadata = tables_module.metadata
```

**Solución Permanente Recomendada**:
Arreglar los imports en `app/infrastructure/__init__.py` y `app/infrastructure/in_memory/__init__.py`.

---

### 5. MySQL Client No Instalado

**Error**:
```bash
mysql: command not found
```

**Impacto**: No se pueden ejecutar scripts SQL de validación directamente.

**Solución**:
```bash
# Windows
# Descargar e instalar MySQL Community Server desde:
# https://dev.mysql.com/downloads/mysql/

# O usar MySQL Workbench para ejecutar los scripts manualmente

# Linux/Mac
sudo apt-get install mysql-client  # Debian/Ubuntu
brew install mysql-client          # macOS
```

---

## ✅ Correcciones Aplicadas Exitosamente

1. ✅ **CircuitBreaker timeout_duration → reset_timeout**
2. ✅ **Comentados imports inexistentes get_async_engine/get_async_session**
3. ✅ **Conftest.py con import directo de metadata**

---

## 🔧 Pasos para Resolver Problemas Restantes

### Paso 1: Arreglar InMemoryStripeGateway

```bash
# Opción A: Revisar qué clase existe
cat app/infrastructure/in_memory/stripe_gateway.py

# Opción B: Comentar el import si no se usa
# En app/infrastructure/in_memory/__init__.py:
# from app.infrastructure.in_memory.stripe_gateway import InMemoryStripeGateway
```

### Paso 2: Verificar Estructura de Imports

```bash
# Ejecutar para ver todos los errores de import
python -c "import app.infrastructure; print('OK')"
```

### Paso 3: Ejecutar Tests Una Vez Arreglado

```bash
# Tests rápidos con SQLite
pytest tests/integration/ -v

# Tests con markers específicos
pytest -m "not integration" -v

# Tests de deadlock sin BD
pytest tests/integration/test_prob_007_deadlock_retry.py::TestPROB007DeadlockDetection -v
```

---

## 📋 Checklist de Validación

Antes de ejecutar tests, verificar:

- [ ] `python -c "from app.infrastructure.circuit_breaker import stripe_breaker; print('OK')"`
- [ ] `python -c "from app.infrastructure.db.tables import metadata; print('OK')"`
- [ ] `python -c "from app.infrastructure.in_memory import InMemoryStripeGateway; print('OK')"`
- [ ] `python -c "from app.main import app; print('OK')"`
- [ ] `pytest --collect-only` (sin errores)

---

## 📊 Resumen de Estado

| Componente                | Estado     | Acción Requerida                    |
|---------------------------|------------|-------------------------------------|
| CircuitBreaker            | ✅ ARREGLADO | Ninguna                             |
| mysql_engine imports      | ✅ ARREGLADO | Ninguna                             |
| InMemoryStripeGateway     | ❌ ERROR    | Crear clase o corregir import       |
| conftest.py               | ⚠️ PARCIAL  | Arreglar después de solucionar #3   |
| MySQL client              | ℹ️ INFO     | Instalar si se necesitan scripts SQL |

---

## 🚀 Tests que SÍ Pueden Ejecutarse (Una Vez Arreglado #3)

```bash
# Tests unitarios de retry (no requieren BD)
pytest tests/integration/test_prob_007_deadlock_retry.py::TestPROB007DeadlockDetection -v

# Tests de detección de errores
pytest tests/integration/test_prob_007_deadlock_retry.py::TestPROB007RetryLogic -v

# Tests de verificación de código
pytest tests/integration/test_prob_001_rollback.py::TestPROB001Integration -v
pytest tests/integration/test_prob_003_dlq.py::TestPROB003DLQBasic -v
```

---

**Última actualización**: 2026-01-21
**Próxima acción**: Resolver error #3 (InMemoryStripeGateway)
