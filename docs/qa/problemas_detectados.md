# Registro de Problemas Detectados - API Reservaciones

**Fecha de Auditoría**: 2026-01-20  
**Documentador**: Sistema Antigravity  
**Fase**: Verificación Post-Implementación  
**Alcance**: Vertical Slice "Reserva y Cobro"

---

## Índice de Problemas

| ID                                                                        | Severidad     | Categoría               | Estado    |
| :------------------------------------------------------------------------ | :------------ | :---------------------- | :-------- |
| [PROB-001](#prob-001-rollback-manual-en-manejo-de-idempotencia)           | 🔴 CRÍTICO    | Transacciones           | Pendiente |
| [PROB-002](#prob-002-ausencia-de-circuit-breaker-para-servicios-externos) | 🟡 IMPORTANTE | Resiliencia             | Pendiente |
| [PROB-003](#prob-003-falta-de-dead-letter-queue-dlq)                      | 🟡 IMPORTANTE | Procesamiento Asíncrono | Pendiente |
| [PROB-004](#prob-004-ausencia-de-global-exception-handler)                | 🟡 IMPORTANTE | Seguridad               | Pendiente |
| [PROB-005](#prob-005-falta-de-timeouts-en-llamadas-externas)              | 🟡 IMPORTANTE | Resiliencia             | Pendiente |
| [PROB-006](#prob-006-ausencia-de-health-checks)                           | 🟢 MEJORA     | Observabilidad          | Pendiente |
| [PROB-007](#prob-007-falta-de-manejo-de-deadlocks)                        | 🟢 MEJORA     | Base de Datos           | Pendiente |

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

### Tests Requeridos

1. Test de apertura de circuito tras 5 fallos consecutivos.
2. Test de recuperación automática tras timeout.

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

---

## Resumen de Acciones Requeridas

### Inmediatas (Esta Semana)

- [ ] **PROB-001**: Corregir rollback manual
- [ ] **PROB-004**: Implementar Global Exception Handler

### Próximo Sprint

- [ ] **PROB-002**: Implementar Circuit Breaker
- [ ] **PROB-003**: Crear Dead Letter Queue
- [ ] **PROB-005**: Configurar Timeouts
- [ ] **PROB-006**: Agregar Health Checks

### Backlog

- [ ] **PROB-007**: Manejo de Deadlocks

---

## Métricas de Seguimiento

| Métrica                             | Objetivo | Actual | Estado |
| :---------------------------------- | :------- | :----- | :----- |
| Problemas Críticos                  | 0        | 1      | 🔴     |
| Problemas Importantes               | < 2      | 4      | 🟡     |
| Cobertura de Tests de Resiliencia   | > 80%    | ~60%   | 🟡     |
| Tiempo Medio de Recuperación (MTTR) | < 5 min  | N/A    | ⚪     |

---

**Última Actualización**: 2026-01-20  
**Próxima Revisión**: 2026-01-27
