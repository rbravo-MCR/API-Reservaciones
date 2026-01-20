# Auditoría de Tolerancia a Fallos - API Reservaciones

**Fecha**: 2026-01-20  
**Auditor**: Sistema Antigravity  
**Alcance**: Vertical Slice "Reserva y Cobro"

---

## 1. Resumen Ejecutivo

El sistema presenta **BUENA tolerancia a fallos** con mecanismos robustos para manejar errores externos. Sin embargo, existen **áreas de mejora** en el manejo de fallos internos y recuperación ante errores de base de datos.

**Calificación General**: ⭐⭐⭐⭐☆ (4/5)

---

## 2. Análisis de Tolerancia a Fallos Externos

### 2.1 Fallos de Stripe (Proveedor de Pago)

#### ✅ Mecanismos Implementados:

1. **Idempotencia de Webhooks** (`handle_stripe_webhook.py:54-59`):
   - Se verifica el `stripe_event_id` antes de procesar.
   - Evita procesamiento duplicado de eventos.

2. **Validación de Firma** (`handle_stripe_webhook.py:35-42`):
   - Verifica la autenticidad del webhook usando `stripe.Webhook.construct_event`.
   - Rechaza payloads inválidos con HTTP 400.

3. **Manejo de Eventos de Fallo** (`handle_stripe_webhook.py:91-108`):
   - Procesa `payment_intent.payment_failed` y actualiza el estado correctamente.

#### ⚠️ Áreas de Mejora:

- **Falta Circuit Breaker**: Si Stripe está caído, no hay mecanismo para evitar llamadas repetidas.
- **Timeout no configurado**: Las llamadas a Stripe no tienen timeout explícito.

**Recomendación**: Implementar un Circuit Breaker pattern y configurar timeouts (5-10s).

---

### 2.2 Fallos de Proveedores Externos (Suppliers)

#### ✅ Mecanismos Implementados:

1. **Patrón Outbox** (`process_outbox_book_supplier.py`):
   - Garantiza que la confirmación con el proveedor se intente incluso si el sistema falla después del pago.
   - Transacción atómica: Pago + Evento Outbox.

2. **Reintentos con Backoff Exponencial** (`process_outbox_book_supplier.py:123-125`):

   ```python
   backoff_seconds = min(BASE_BACKOFF_SECONDS * (2 ** (attempts - 1)), 300)
   ```

   - Hasta 5 intentos con backoff exponencial (15s, 30s, 60s, 120s, 240s).

3. **Estado de Fallback** (`CONFIRMED_INTERNAL`):
   - Si el proveedor falla permanentemente, la reserva NO se cancela.
   - Se marca como `ON_REQUEST` para gestión manual.

4. **Auditoría Completa** (`supplier_request_repo`):
   - Cada intento se registra en `reservation_supplier_requests`.
   - Incluye: request_payload, response_payload, error_code, http_status.

#### ⚠️ Áreas de Mejora:

- **Falta Dead Letter Queue (DLQ)**: Los eventos fallidos permanentemente no se mueven a una cola especial.
- **No hay alertas automáticas**: Cuando se alcanza MAX_ATTEMPTS, solo se loguea el error.

**Recomendación**:

- Implementar DLQ para eventos fallidos.
- Integrar alertas (email/Slack) cuando una reserva queda en `ON_REQUEST` permanentemente.

---

## 3. Análisis de Tolerancia a Fallos Internos

### 3.1 Fallos de Base de Datos

#### ✅ Mecanismos Implementados:

1. **Transacciones ACID** (`transaction_manager.py`):
   - Uso de `async with session.begin()` garantiza atomicidad.
   - Si falla cualquier operación, se hace rollback automático.

2. **Optimistic Locking** (Implementado en repositorios):
   - Se usa `expected_lock_version` para evitar condiciones de carrera.
   - Ejemplo: `update_payment_status(..., expected_lock_version=...)`.

3. **Idempotencia de API** (`pay_reservation.py:63-71`):
   - Tabla `idempotency_keys` previene ejecuciones duplicadas.
   - Detecta conflictos de payload (HTTP 409).

#### ❌ Problemas Detectados:

1. **Rollback Manual Incorrecto** (`repository.py:58`):

   ```python
   except IntegrityError:
       await self.session.rollback()  # ❌ PELIGROSO
       return
   ```

   - El rollback manual puede causar inconsistencias si hay transacciones anidadas.
   - **Impacto**: Si el webhook falla después del rollback, el pago podría quedar en estado inconsistente.

2. **Falta Manejo de Deadlocks**:
   - No hay retry logic para errores de deadlock de MySQL.
   - **Impacto**: Una transacción podría fallar permanentemente por un deadlock temporal.

3. **No hay Health Checks de BD**:
   - No existe un endpoint `/health/db` para verificar conectividad.

**Recomendación CRÍTICA**:

```python
# ❌ ELIMINAR el rollback manual
except IntegrityError:
    # Dejar que la transacción padre maneje el rollback
    return  # Idempotencia detectada, salir silenciosamente
```

---

### 3.2 Fallos de Aplicación (Excepciones No Controladas)

#### ✅ Mecanismos Implementados:

1. **Logging Estructurado**:
   - Uso de `logger.error/warning/info` con contexto extra.
   - Facilita debugging en producción.

2. **HTTPException para Errores de Negocio**:
   - Códigos HTTP apropiados (404, 409, 400).
   - Mensajes descriptivos para el cliente.

#### ⚠️ Áreas de Mejora:

- **Falta Global Exception Handler**:
  - Excepciones no controladas devuelven stack traces al cliente (riesgo de seguridad).
- **No hay Retry en Operaciones Críticas**:
  - Si `stripe_gateway.confirm_payment` falla por timeout, no se reintenta.

**Recomendación**:

```python
# Agregar en main.py
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error("Unhandled exception", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )
```

---

## 4. Análisis de Consistencia de Datos

### ✅ Fortalezas:

1. **Outbox Pattern**: Garantiza consistencia eventual entre pago y confirmación de proveedor.
2. **Idempotencia Robusta**: Previene duplicados en webhooks y API calls.
3. **Lock Version**: Evita lost updates en actualizaciones concurrentes.

### ⚠️ Debilidades:

1. **Falta Saga Pattern**: Si el pago falla DESPUÉS de confirmar con el proveedor (caso raro), no hay compensación automática.
2. **No hay Event Sourcing**: Dificulta auditoría de cambios de estado.

---

## 5. Pruebas de Resiliencia

### ✅ Tests Existentes:

- `test_reservation_flow.py`: Valida flujo completo.
- `test_fallback_manual.py`: Simula fallo de proveedor.
- `test_qa_suite.py`: Pruebas de concurrencia e idempotencia.

### ❌ Tests Faltantes:

1. **Chaos Engineering**: No hay tests que simulen:
   - Caída de BD en medio de transacción.
   - Timeout de Stripe.
   - Deadlocks de MySQL.

2. **Load Testing**: No se ha verificado comportamiento bajo carga (1000+ req/s).

**Recomendación**: Implementar tests con `pytest-timeout` y `pytest-asyncio` para simular fallos.

---

## 6. Recomendaciones Priorizadas

### 🔴 CRÍTICO (Implementar YA):

1. **Eliminar rollback manual** en `repository.py:58`.
2. **Agregar Global Exception Handler** en FastAPI.
3. **Configurar timeouts** en llamadas a Stripe (5-10s).

### 🟡 IMPORTANTE (Próximo Sprint):

4. Implementar **Circuit Breaker** para Stripe y Suppliers.
5. Agregar **Dead Letter Queue** para eventos fallidos.
6. Crear **Health Check** endpoint (`/health/db`).

### 🟢 MEJORA (Backlog):

7. Implementar **Saga Pattern** para compensaciones.
8. Agregar **Chaos Engineering** tests.
9. Configurar **Alertas** (Slack/Email) para fallos permanentes.

---

## 7. Conclusión

El sistema tiene una **arquitectura de resiliencia sólida** para fallos externos, especialmente con el Outbox Pattern y reintentos. Sin embargo, requiere mejoras en:

- Manejo de fallos internos (rollback manual, deadlocks).
- Observabilidad (alertas, health checks).
- Pruebas de caos.

**Estado Actual**: APTO para producción con **monitoreo activo** y plan de mejora continua.
