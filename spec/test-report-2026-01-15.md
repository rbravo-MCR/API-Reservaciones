# Reporte de Pruebas - 2026-01-15

## Contexto
- Comando: `uv run pytest -q`
- Entorno: modo in-memory (`USE_IN_MEMORY=true` por defecto), sin base de datos externa.
- Objetivo: verificar flujos principales de creación/pago de reservas, webhook de Stripe, recibo y worker de proveedor tras ajustes de webhook/outbox.

## Resultados
- Estado: **Exitoso** (16 pruebas aprobadas).
- Warnings observados:
  - `json_encoders` de Pydantic está deprecado (sin impacto funcional actual).
  - Uso de `datetime.utcnow()` en outbox/worker; recomendado migrar a `datetime.now(timezone.utc)` para evitar deprecación.
  - Pytest no pudo escribir en `.pytest_cache` por permisos; no afecta ejecución.

## Hallazgos
- El flujo de recibo responde 409 si la reserva no está confirmada, según lo esperado.
- El worker de proveedor confirma la reserva y persiste código de proveedor en in-memory.

## Pendientes/Seguimientos
- Si se desea ejecutar en modo SQL, configurar `.env` con `USE_IN_MEMORY=false` y `DATABASE_URL` válido.
- Considerar reemplazar `datetime.utcnow()` por objetos timezone-aware para limpiar warnings.
