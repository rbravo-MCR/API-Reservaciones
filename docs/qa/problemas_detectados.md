# Registro de Problemas Detectados - API Reservaciones

**Fecha de Auditoría**: 2026-01-20  
**Documentador**: Sistema Antigravity  
**Fase**: Verificación Post-Implementación  
**Alcance**: Vertical Slice "Reserva y Cobro"

---

## Índice de Problemas

| ID                                                                        | Severidad     | Categoría               | Estado    |
| :------------------------------------------------------------------------ | :------------ | :---------------------- | :-------- |
| [PROB-001](#prob-001-rollback-manual-en-manejo-de-idempotencia)           | 🔴 CRÍTICO    | Transacciones           | ✅ RESUELTO |
| [PROB-002](#prob-002-ausencia-de-circuit-breaker-para-servicios-externos) | 🟡 IMPORTANTE | Resiliencia             | ✅ RESUELTO |
| [PROB-003](#prob-003-falta-de-dead-letter-queue-dlq)                      | 🟡 IMPORTANTE | Procesamiento Asíncrono | ✅ RESUELTO |
| [PROB-004](#prob-004-ausencia-de-global-exception-handler)                | 🟡 IMPORTANTE | Seguridad               | ✅ RESUELTO |
| [PROB-005](#prob-005-falta-de-timeouts-en-llamadas-externas)              | 🟡 IMPORTANTE | Resiliencia             | ✅ RESUELTO |
| [PROB-006](#prob-006-ausencia-de-health-checks)                           | 🟢 MEJORA     | Observabilidad          | ✅ RESUELTO |
| [PROB-007](#prob-007-falta-de-manejo-de-deadlocks)                        | 🟢 MEJORA     | Base de Datos           | ✅ RESUELTO |

---

## PROB-001: Rollback Manual en Manejo de Idempotencia

### Severidad

🔴 **CRÍTICO** - Puede causar inconsistencia de datos en producción.

### Descripción Técnica

En el archivo `app/infrastructure/db/repository.py`, línea 58, existe un rollback manual dentro de un bloque `try-except` que maneja `IntegrityError`:

```python
# Archivo: app/infrastructure/db/repository.py
# Líneas: 50-59

try:
    self.session.add(payment)
    await self.session.flush()  # Force insert to check constraint
except IntegrityError:
    # Duplicate payment -> Idempotent success
    await self.session.rollback()  # ❌ PROBLEMA AQUÍ
    return
```

**Contexto**: Este código se ejecuta dentro del método `mark_as_paid_and_enqueue_confirmation`, que es llamado desde el webhook de Stripe.

### Impacto

#### Impacto Técnico

1. **Inconsistencia Transaccional**: Si este método se ejecuta dentro de una transacción padre (lo cual es el caso en el flujo de webhook), el rollback manual puede:
   - Deshacer cambios de la transacción padre que ya se habían confirmado.
   - Dejar la sesión de SQLAlchemy en un estado inconsistente.

2. **Pérdida de Atomicidad**: El patrón Outbox requiere que el pago y el evento se guarden en la misma transacción. Un rollback parcial rompe esta garantía.

#### Impacto en el Negocio

- **Escenario de Fallo**: Un cliente paga, Stripe confirma, pero el evento Outbox no se guarda debido al rollback.
- **Consecuencia**: La reserva queda en estado `PAID` pero nunca se intenta confirmar con el proveedor.
- **Costo**: Pérdida de venta + mala experiencia de usuario + carga operativa manual.

### Ubicación en el Código

| Archivo                               | Línea | Método                                  |
| :------------------------------------ | :---- | :-------------------------------------- |
| `app/infrastructure/db/repository.py` | 58    | `mark_as_paid_and_enqueue_confirmation` |

### Solución Propuesta

#### Opción 1: Eliminar Rollback Manual (RECOMENDADA)

```python
# ✅ CORRECCIÓN
try:
    self.session.add(payment)
    await self.session.flush()
except IntegrityError:
    # Duplicate payment -> Idempotent success
    # Dejar que la transacción padre maneje el rollback si es necesario
    return  # Salir silenciosamente
```

**Justificación**: La transacción padre (`async with session.begin()`) ya maneja rollbacks automáticamente en caso de error. El rollback manual es redundante y peligroso.

#### Opción 2: Usar Savepoint (Alternativa)

```python
# Alternativa con savepoint
savepoint = await self.session.begin_nested()
try:
    self.session.add(payment)
    await self.session.flush()
    await savepoint.commit()
except IntegrityError:
    await savepoint.rollback()
    return
```

### Prioridad de Implementación

**INMEDIATA** - Debe corregirse antes de desplegar a producción.

### Estado de Resolución

✅ **RESUELTO** - 2026-01-21

**Cambios Aplicados:**
- Eliminado el `await self.session.rollback()` en `app/infrastructure/db/repository.py:58`
- Actualizado comentario para explicar que la transacción padre maneja el rollback
- Verificado que otros rollbacks en `endpoints.py` son correctos (nivel de endpoint)

**Archivo Modificado:**
- `app/infrastructure/db/repository.py` - Método `mark_as_paid_and_enqueue_confirmation`

### Tests Requeridos

1. Test de idempotencia de webhook con transacción activa.
2. Test de concurrencia: 2 webhooks simultáneos con mismo `payment_id`.
3. Test de rollback: Verificar que el evento Outbox se guarda correctamente.

### Referencias

- ADR-002: Manejo de Fallos Distribuidos
- Documentación SQLAlchemy: [Session Basics](https://docs.sqlalchemy.org/en/14/orm/session_basics.html)

---

## PROB-002: Ausencia de Circuit Breaker para Servicios Externos

### Severidad

🟡 **IMPORTANTE** - Puede causar degradación del servicio bajo carga.

### Descripción Técnica

Las llamadas a servicios externos (Stripe, Suppliers) no implementan el patrón Circuit Breaker. Si un servicio externo está caído o lento, el sistema seguirá intentando llamadas que fallarán, consumiendo recursos.

**Archivos Afectados**:

- `app/infrastructure/gateways/stripe_gateway_real.py`
- `app/infrastructure/gateways/supplier_gateway_http.py`

### Impacto

#### Impacto Técnico

1. **Cascading Failures**: Si Stripe está caído, todas las peticiones de pago fallarán, bloqueando threads.
2. **Resource Exhaustion**: Conexiones HTTP abiertas sin timeout pueden agotar el pool de conexiones.
3. **Latencia Elevada**: Usuarios experimentarán timeouts de 30-60 segundos.

#### Impacto en el Negocio

- Pérdida de conversión durante incidentes de proveedores externos.
- Mala experiencia de usuario (timeouts largos).

### Solución Propuesta

Implementar Circuit Breaker usando la librería `pybreaker`:

```python
# Nuevo archivo: app/infrastructure/circuit_breaker.py
from pybreaker import CircuitBreaker

stripe_breaker = CircuitBreaker(
    fail_max=5,
    timeout_duration=60,
    name="stripe_circuit_breaker"
)

# En stripe_gateway_real.py
@stripe_breaker
async def confirm_payment(self, ...):
    # Código existente
```

### Prioridad de Implementación

**ALTA** - Implementar en el próximo sprint.

### Estado de Resolución

✅ **RESUELTO** - 2026-01-21

**Cambios Aplicados:**

1. **Dependencias** (`pyproject.toml`):
   - Agregada librería `pybreaker>=1.0.0,<2.0.0`

2. **Módulo Centralizado** (`app/infrastructure/circuit_breaker.py`):
   - Creado módulo con configuración centralizada de Circuit Breakers
   - Configurado `stripe_breaker` con fail_max=5, timeout_duration=60s
   - Configurado `supplier_breaker` con fail_max=5, timeout_duration=60s
   - Agregados listeners para logging de cambios de estado
   - Documentación completa del patrón (CLOSED → OPEN → HALF_OPEN)

3. **Stripe Gateway** (`app/infrastructure/gateways/stripe_gateway_real.py`):
   - Envuelto `stripe.PaymentIntent.create` con `stripe_breaker.call()`
   - Manejo explícito de `CircuitBreakerError` con logging estructurado
   - Documentación de excepciones en docstring

4. **Supplier Gateway** (`app/infrastructure/gateways/supplier_gateway_http.py`):
   - Envuelto método `book()` con `supplier_breaker.call_async()`
   - Nuevo error code `CIRCUIT_OPEN` para cuando el circuito está abierto
   - Logging estructurado para todos los estados del circuit breaker
   - Manejo de CircuitBreakerError retorna SupplierBookingResult con FAILED

**Configuración del Circuit Breaker:**
- **Threshold**: 5 fallos consecutivos abren el circuito
- **Timeout**: 60 segundos en estado OPEN antes de intentar recovery (HALF_OPEN)
- **Estados**: CLOSED (normal) → OPEN (falla rápido) → HALF_OPEN (testeo)
- **Listeners**: Log automático de cambios de estado para alerting

**Beneficios:**
- Previene cascading failures ante caída de servicios externos
- Falla rápido cuando el servicio está caído (no consume recursos inútilmente)
- Recovery automático cuando el servicio se recupera
- Logging estructurado para monitoring y alerting
- Protege el sistema de resource exhaustion

**Archivos Creados:**
- `app/infrastructure/circuit_breaker.py` - Configuración centralizada

**Archivos Modificados:**
- `pyproject.toml` - Dependencia pybreaker agregada
- `app/infrastructure/gateways/stripe_gateway_real.py` - Circuit breaker aplicado
- `app/infrastructure/gateways/supplier_gateway_http.py` - Circuit breaker aplicado

### Tests Requeridos

1. Test de apertura de circuito tras 5 fallos consecutivos.
2. Test de recuperación automática tras timeout.
3. Test de comportamiento en estado HALF_OPEN (permite 1 request para testing)
4. Test de logging de cambios de estado

---

## PROB-003: Falta de Dead Letter Queue (DLQ)

### Severidad

🟡 **IMPORTANTE** - Dificulta la gestión de errores permanentes.

### Descripción Técnica

Los eventos de Outbox que fallan permanentemente (5 intentos agotados) se marcan como `FAILED` pero permanecen en la misma tabla. No hay un mecanismo para moverlos a una cola especial para análisis.

**Ubicación**: `app/application/use_cases/process_outbox_book_supplier.py:126-134`

### Impacto

#### Impacto Operativo

1. **Dificulta Monitoreo**: No es fácil identificar reservas que requieren intervención manual.
2. **Riesgo de Pérdida**: Los eventos fallidos pueden ser sobrescritos o eliminados accidentalmente.

### Solución Propuesta

Crear tabla `outbox_dead_letters`:

```sql
CREATE TABLE outbox_dead_letters (
    id INT PRIMARY KEY AUTO_INCREMENT,
    original_event_id INT,
    reservation_code VARCHAR(50),
    event_type VARCHAR(64),
    payload JSON,
    error_code VARCHAR(64),
    error_message VARCHAR(255),
    attempts INT,
    moved_at DATETIME
);
```

Modificar `process_outbox_book_supplier.py`:

```python
if attempts >= MAX_ATTEMPTS:
    await self._outbox_repo.move_to_dlq(event.id)
    await self._alert_service.notify_ops(
        f"Reservation {reservation_code} requires manual intervention"
    )
```

### Prioridad de Implementación

**MEDIA** - Implementar en el próximo sprint.

### Estado de Resolución

✅ **RESUELTO** - 2026-01-21

**Cambios Aplicados:**

1. **Modelo de Base de Datos** (`app/infrastructure/db/models.py`):
   - Creado `OutboxDeadLetterModel` con todos los campos necesarios
   - Incluye índices en `original_event_id` y `reservation_code`
   - Campos de auditoría: `moved_at`, `created_at`
   - Campos de contexto: `error_code`, `error_message`, `attempts`

2. **Esquema de Tabla** (`app/infrastructure/db/tables.py`):
   - Agregada tabla `outbox_dead_letters` con 12 columnas
   - Soporte completo para JSON payload
   - Timestamps automáticos

3. **Interface de Repositorio** (`app/application/interfaces/outbox_repo.py`):
   - Agregado método `move_to_dlq(event, error_code, error_message)`
   - Documentación completa del propósito

4. **Implementación SQL** (`app/infrastructure/db/repositories/outbox_repo_sql.py`):
   - Implementado `move_to_dlq` con lógica completa:
     - Inserta evento en `outbox_dead_letters`
     - Marca evento original como FAILED
     - Extrae `reservation_code` del payload
     - Logging estructurado con nivel WARNING

5. **Use Case de Procesamiento** (`app/application/use_cases/process_outbox_book_supplier.py`):
   - Integrado DLQ cuando `attempts >= MAX_ATTEMPTS` (5 intentos)
   - Reemplazado `mark_failed` por `move_to_dlq`
   - Logging con nivel CRITICAL para alertas operacionales
   - Mensaje explícito: "REQUIRES MANUAL INTERVENTION"

**Flujo Implementado:**

```
Outbox Event (attempts = 1-4)
    ↓ FAILED
Retry con backoff exponencial
    ↓ FAILED (attempts = 5)
move_to_dlq()
    ├─→ INSERT INTO outbox_dead_letters
    ├─→ UPDATE outbox_events SET status='FAILED'
    └─→ logger.critical("REQUIRES MANUAL INTERVENTION")
```

**Beneficios:**

- ✅ **Previene Pérdida de Datos**: Eventos fallidos preservados para análisis
- ✅ **Facilita Monitoreo**: Query simple para identificar reservas problemáticas
- ✅ **Soporte Operacional**: Contexto completo para intervención manual
- ✅ **Alerting Integrado**: Logs CRITICAL disparan alertas automáticas
- ✅ **Auditoría Completa**: Rastro completo de intentos y errores

**Consulta para Monitoreo:**

```sql
-- Eventos en DLQ que requieren atención
SELECT
    id,
    reservation_code,
    event_type,
    error_code,
    error_message,
    attempts,
    moved_at
FROM outbox_dead_letters
WHERE moved_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
ORDER BY moved_at DESC;
```

**Archivos Creados:**
- N/A (modificaciones a archivos existentes)

**Archivos Modificados:**
- `app/infrastructure/db/models.py` - Modelo OutboxDeadLetterModel
- `app/infrastructure/db/tables.py` - Tabla outbox_dead_letters
- `app/application/interfaces/outbox_repo.py` - Interface con move_to_dlq
- `app/infrastructure/db/repositories/outbox_repo_sql.py` - Implementación move_to_dlq
- `app/application/use_cases/process_outbox_book_supplier.py` - Integración DLQ

---

## PROB-004: Ausencia de Global Exception Handler

### Severidad

🟡 **IMPORTANTE** - Riesgo de seguridad y mala experiencia de usuario.

### Descripción Técnica

FastAPI no tiene configurado un manejador global de excepciones. Las excepciones no controladas devuelven stack traces completos al cliente, exponiendo información sensible del sistema.

### Impacto

#### Impacto de Seguridad

- **Information Disclosure**: Stack traces revelan estructura de código, rutas de archivos, versiones de librerías.
- **Compliance**: Viola mejores prácticas de OWASP.

#### Impacto en UX

- Mensajes de error técnicos confunden a usuarios finales.

### Solución Propuesta

Agregar en `app/main.py`:

```python
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception",
        exc_info=exc,
        extra={
            "path": request.url.path,
            "method": request.method,
        }
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error_id": str(uuid.uuid4())  # Para tracking
        }
    )
```

### Prioridad de Implementación

**ALTA** - Implementar antes de producción.

### Estado de Resolución

✅ **RESUELTO** - 2026-01-21

**Cambios Aplicados:**
- Implementado Global Exception Handler en `app/main.py`
- Configurado logging estructurado con contexto (error_id, path, method, client_host)
- Eliminado `traceback.print_exc()` de `app/api/endpoints.py`
- Reemplazado prints por logging en use cases:
  - `app/application/use_cases/handle_webhook.py` - logger.warning para metadata faltante
  - `app/application/use_cases/process_outbox.py` - logger.error para errores de procesamiento

**Funcionalidades Implementadas:**
- Generación automática de `error_id` UUID para tracking
- Logs estructurados con contexto completo para debugging interno
- Respuestas genéricas al cliente sin exponer detalles internos
- Cumplimiento con mejores prácticas de OWASP

**Archivos Modificados:**
- `app/main.py` - Global Exception Handler
- `app/api/endpoints.py` - Eliminado traceback.print_exc
- `app/application/use_cases/handle_webhook.py` - Logging estructurado
- `app/application/use_cases/process_outbox.py` - Logging estructurado

---

## PROB-005: Falta de Timeouts en Llamadas Externas

### Severidad

🟡 **IMPORTANTE** - Puede causar bloqueos indefinidos.

### Descripción Técnica

Las llamadas a Stripe y Suppliers no tienen timeouts configurados explícitamente.

**Archivos Afectados**:

- `app/infrastructure/gateways/stripe_gateway_real.py:22-28`
- `app/infrastructure/gateways/supplier_gateway_http.py`

### Solución Propuesta

```python
# En stripe_gateway_real.py
import httpx

async def confirm_payment(self, ...):
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Usar cliente HTTP con timeout
```

Para Stripe SDK (síncrono):

```python
stripe.max_network_retries = 2
stripe.api_base = "https://api.stripe.com"
# Nota: Stripe SDK no soporta timeout async, considerar migrar a httpx
```

### Prioridad de Implementación

**ALTA** - Implementar en el próximo sprint.

### Estado de Resolución

✅ **RESUELTO** - 2026-01-21

**Cambios Aplicados:**

1. **Stripe Gateway** (`app/infrastructure/gateways/stripe_gateway_real.py`):
   - Configurado `stripe.max_network_retries = 2` para reintentos automáticos
   - Configurado `stripe.default_http_client` con timeout de 10.0 segundos
   - Agregados comentarios explicando la limitación del SDK síncrono de Stripe

2. **Supplier Gateway** (`app/infrastructure/gateways/supplier_gateway_http.py`):
   - Aumentado timeout por defecto de 5.0 → 10.0 segundos para producción
   - Agregada documentación en el docstring del __init__
   - El timeout ya estaba implementado correctamente con httpx.AsyncClient

**Configuración de Timeouts:**
- **Stripe API**: 10 segundos + 2 reintentos automáticos
- **Supplier APIs**: 10 segundos (configurable por instancia)
- Ambos gateways manejan TimeoutException apropiadamente

**Beneficios:**
- Previene bloqueos indefinidos en llamadas externas
- Mejora la resiliencia ante servicios lentos o caídos
- Tiempo máximo de espera predecible para el usuario
- Compatibilidad con SLAs de producción

**Archivos Modificados:**
- `app/infrastructure/gateways/stripe_gateway_real.py` - Timeout y retries configurados
- `app/infrastructure/gateways/supplier_gateway_http.py` - Timeout aumentado a 10s

---

## PROB-006: Ausencia de Health Checks

### Severidad

🟢 **MEJORA** - Dificulta monitoreo en producción.

### Descripción Técnica

No existe un endpoint `/health` que verifique:

- Conectividad a la base de datos.
- Conectividad a Stripe.
- Estado del sistema de archivos.

### Solución Propuesta

```python
# En app/api/routers/health.py
@router.get("/health")
async def health_check():
    return {"status": "ok"}

@router.get("/health/db")
async def health_db(session: AsyncSession = Depends(get_db_session)):
    try:
        await session.execute(text("SELECT 1"))
        return {"status": "healthy"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)}
        )
```

### Prioridad de Implementación

**MEDIA** - Implementar antes de producción.

### Estado de Resolución

✅ **RESUELTO** - 2026-01-21

**Cambios Aplicados:**

1. **Router de Health Checks** (`app/api/routers/health.py`) ⭐ NUEVO:
   - Creado router completo con múltiples endpoints de health check
   - Documentación completa para cada endpoint

2. **Endpoints Implementados**:
   - **GET /health**: Liveness probe básico (siempre 200 OK)
   - **GET /health/live**: Alias para /health (convención K8s)
   - **GET /health/db**: Verifica conectividad con base de datos (503 si falla)
   - **GET /health/ready**: Readiness probe completo (verifica todas las dependencias)

3. **Integración** (`app/main.py`):
   - Registrado health_router con tag "Health"
   - Eliminado endpoint /health básico anterior
   - Sin prefijo /api/v1 (health checks se sirven desde root)

**Funcionalidad de Cada Endpoint:**

| Endpoint | Propósito | K8s Probe | Status Code |
|:---------|:----------|:----------|:------------|
| `/health` | Liveness | ✅ | 200 siempre |
| `/health/live` | Liveness (alias) | ✅ | 200 siempre |
| `/health/db` | DB Check | - | 200 OK / 503 Error |
| `/health/ready` | Readiness | ✅ | 200 Ready / 503 Not Ready |

**Uso con Kubernetes:**

```yaml
# Liveness Probe (restart si falla)
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 30

# Readiness Probe (controla tráfico)
readinessProbe:
  httpGet:
    path: /health/ready
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
```

**Beneficios:**
- ✅ Liveness probe detecta pods no responsivos → restart automático
- ✅ Readiness probe controla tráfico → no envía requests a pods no listos
- ✅ Health check de DB previene tráfico a instancias sin conectividad
- ✅ Logging estructurado de fallos de health checks
- ✅ Respuestas JSON detalladas con información de cada componente

**Archivos Creados:**
- `app/api/routers/health.py` - Router completo de health checks

**Archivos Modificados:**
- `app/main.py` - Registro del router de health

---

## PROB-007: Falta de Manejo de Deadlocks

### Severidad

🟢 **MEJORA** - Puede causar fallos esporádicos.

### Descripción Técnica

No hay lógica de retry para errores de deadlock de MySQL (`1213 Deadlock found`).

### Solución Propuesta

```python
from sqlalchemy.exc import OperationalError

MAX_RETRIES = 3

for attempt in range(MAX_RETRIES):
    try:
        async with session.begin():
            # Operación transaccional
            break
    except OperationalError as e:
        if "1213" in str(e) and attempt < MAX_RETRIES - 1:
            await asyncio.sleep(0.1 * (2 ** attempt))
            continue
        raise
```

### Prioridad de Implementación

**BAJA** - Backlog.

### Estado de Resolución

✅ **RESUELTO** - 2026-01-21

**Cambios Aplicados:**

1. **Módulo de Retry** (`app/infrastructure/db/retry.py`):
   - Creado módulo dedicado con función `retry_on_deadlock()` para manejo automático de deadlocks
   - Implementada función `is_deadlock_error()` que detecta errores MySQL 1213 (Deadlock) y 1205 (Lock wait timeout)
   - Soporta reintentos configurables con exponential backoff: `base_delay * (2 ** attempt)`
   - Logging estructurado con nivel WARNING en cada retry y ERROR si se exceden los intentos máximos
   - Incluye decorator `@with_deadlock_retry` para uso conveniente

2. **Endpoints Críticos** (Protegidos con retry de deadlocks):
   - `app/api/endpoints.py::create_reservation` - Creación de reservaciones con 3 intentos, delay base 0.1s
   - `app/api/endpoints.py::stripe_webhook` - Webhook de Stripe con 3 intentos, delay base 0.1s
   - `app/api/routers/worker.py::process_outbox_book_supplier` - Procesamiento outbox con 3 intentos, delay base 0.1s

**Configuración de Retry:**
- **Max Attempts**: 3 intentos por operación
- **Base Delay**: 0.1 segundos (exponencial: 0.1s → 0.2s → 0.4s)
- **Errores Detectados**: MySQL 1213 (Deadlock) y 1205 (Lock wait timeout)
- **Comportamiento**: Re-lanza excepciones no-deadlock inmediatamente

**Ejemplo de Uso:**
```python
async def execute_create():
    try:
        response = await use_case.execute(request)
        await session.commit()
        return response
    except Exception as e:
        await session.rollback()
        raise

return await retry_on_deadlock(execute_create, max_attempts=3, base_delay=0.1)
```

**Beneficios:**
- Resuelve automáticamente deadlocks transitorios sin intervención manual
- Reduce fallos esporádicos en operaciones concurrentes
- Logging detallado para debugging y monitoreo
- Patrón reutilizable para futuros endpoints críticos
- Compatible con el manejo de excepciones existente (HTTPException, etc.)

**Archivos Creados:**
- `app/infrastructure/db/retry.py` - Utilidad de retry con exponential backoff

**Archivos Modificados:**
- `app/api/endpoints.py` - Retry en create_reservation y stripe_webhook
- `app/api/routers/worker.py` - Retry en process_outbox_book_supplier

---

## Resumen de Acciones Requeridas

### Inmediatas (Esta Semana)

- [x] **PROB-001**: Corregir rollback manual ✅ COMPLETADO (2026-01-21)
- [x] **PROB-004**: Implementar Global Exception Handler ✅ COMPLETADO (2026-01-21)

### Próximo Sprint

- [x] **PROB-002**: Implementar Circuit Breaker ✅ COMPLETADO (2026-01-21)
- [x] **PROB-003**: Crear Dead Letter Queue ✅ COMPLETADO (2026-01-21)
- [x] **PROB-005**: Configurar Timeouts ✅ COMPLETADO (2026-01-21)
- [x] **PROB-006**: Agregar Health Checks ✅ COMPLETADO (2026-01-21)

### Backlog

- [x] **PROB-007**: Manejo de Deadlocks ✅ COMPLETADO (2026-01-21)

---

## Métricas de Seguimiento

| Métrica                             | Objetivo | Actual | Estado |
| :---------------------------------- | :------- | :----- | :----- |
| Problemas Críticos                  | 0        | 0      | 🟢     |
| Problemas Importantes               | < 2      | 0      | 🟢 ⭐   |
| Cobertura de Tests de Resiliencia   | > 80%    | ~60%   | 🟡     |
| Tiempo Medio de Recuperación (MTTR) | < 5 min  | N/A    | ⚪     |

---

**Última Actualización**: 2026-01-21
**Próxima Revisión**: 2026-01-27

---

## Historial de Cambios

### 2026-01-21
- ✅ **PROB-001 RESUELTO**: Eliminado rollback manual en `repository.py:58` que causaba inconsistencia transaccional
- ✅ **PROB-004 RESUELTO**: Implementado Global Exception Handler y logging estructurado en toda la aplicación
- ✅ **PROB-005 RESUELTO**: Configurados timeouts en todos los gateways externos (Stripe 10s + Supplier 10s)
- ✅ **PROB-002 RESUELTO**: Implementado Circuit Breaker con pybreaker para Stripe y Suppliers (fail_max=5, timeout=60s)
- ✅ **PROB-006 RESUELTO**: Implementados health checks completos (/health, /health/db, /health/ready, /health/live)
- ✅ **PROB-003 RESUELTO**: Implementado Dead Letter Queue completo con tabla, repositorio y logging CRITICAL
- ✅ **PROB-007 RESUELTO**: Implementado retry automático de deadlocks con exponential backoff (3 intentos, MySQL 1213/1205)
- 📊 Problemas Críticos: 1 → 0 🎯 **100% eliminados**
- 📊 Problemas Importantes: 4 → 0 ⭐ **100% resueltos** (objetivo: < 2)
- 📊 Problemas Mejora: 2 → 0 🎯 **100% resueltos**
- 🏆 **SESIÓN COMPLETA**: 7 problemas resueltos | **100% reducción total** 🎉
