# Reporte de Pruebas - 2026-01-15 (snapshot SQL recibo)

## Contexto
- Cambios validados: snapshot de oficinas/supplier/producto en `ReceiptQuerySQL` con lookups opcionales; validaciones de referencias en `ReservationRepoSQL` ya agregadas; tests en modo in-memory.
- Comando: `uv run pytest -q`
- Entorno: in-memory (`USE_IN_MEMORY=true`), sin DB externa.

## Resultados
- Estado: **Exitoso** (16 pruebas aprobadas).
- Warnings: deprecación `json_encoders` (Pydantic) y permisos de `.pytest_cache` (no afecta ejecución).

## Notas
- `ReceiptQuerySQL` ahora intenta traer `code/name` de oficinas y `name` de supplier; usa `external_code` de `supplier_car_products` como acriss si existe. En modo SQL, requiere que las tablas `offices`, `suppliers`, `supplier_car_products` existan.
- Validaciones de referencias en creación de reservas permanecen (supplier, oficinas, car_category, sales_channel, supplier_car_product opcional).

## Recomendaciones
- Si se ejecuta en modo SQL, alinear el esquema con las tablas consultadas y crear migraciones para cualquier cambio pendiente en `outbox_events` y referencias requeridas.
