# Reglas de Negocio - Reservation Backend

Este documento detalla las reglas de negocio aplicadas al flujo de "Crear Reserva y Cobro".

## 1. Alcance y Exclusiones

- **Alcance**: Creación de Reserva y Procesamiento de Pago.
- **Exclusiones**: No Auth, No Cancelación, No Disponibilidad.

## 2. Identificación y Generación de Código

- **Código Único Inmediato**: Se genera un `reservation_code` de 8 caracteres alfanuméricos al recibir la solicitud.
- **Supplier y Oficinas**: `supplier_id` es obligatorio. `pickup_office_id` y `dropoff_office_id` deben pertenecer al mismo supplier.

## 3. Vehículo y Categoría

- **Categoría Obligatoria**: `car_category_id` es el mínimo requerido.
- **Mapeo ACRISS**: Los códigos ACRISS deben ser resueltos a categorías internas por el Adapter.

## 4. Fechas y Validación

- **Consistencia**: `pickup_datetime` < `dropoff_datetime`.
- **Antelación**: `pickup_datetime` debe cumplir con la antelación mínima configurada.
- **Timezones**:
  - Almacenamiento en **UTC**.
  - Persistencia de `timezone_offset` para reconstrucción de hora local.
  - Validaciones de horario de apertura en hora local.

## 5. Máquina de Estados

| Paso            | Estado Reserva (`status`) | Estado Pago (`payment_status`) | Descripción                                    |
| :-------------- | :------------------------ | :----------------------------- | :--------------------------------------------- |
| 1. Creación     | `DRAFT`                   | `PENDING`                      | Reserva creada, esperando pago.                |
| 2. Checkout     | `PENDING_PAYMENT`         | `PENDING`                      | PaymentIntent generado.                        |
| 3. Pago OK      | `PENDING_SUPPLIER`        | `PAID`                         | Webhook recibido. Inicia proceso con Supplier. |
| 4. Confirmación | `CONFIRMED`               | `PAID`                         | Supplier confirmó con código externo.          |
| 5. Fallback     | `CONFIRMED_INTERNAL`      | `PAID`                         | Supplier falló. Confirmación interna.          |

**Regla de Oro**: Una vez que el pago es `PAID`, la reserva no se cancela automáticamente por error técnico; pasa a `CONFIRMED_INTERNAL`.

## 6. Pago con Stripe

- **Idempotencia**: Uso de `stripe_event_id` para evitar duplicados.
- **Validación**: El estado `PAID` solo se establece tras `payment_intent.succeeded`.

## 7. Integración con Supplier

- **Patrón Adapter**: Normalización de Request/Response para diferentes proveedores.
- **Auditoría**: Registro de toda interacción en `reservation_supplier_requests`.
- **Manejo de Fallos**: Si el proveedor falla tras el pago, se marca como `CONFIRMED_INTERNAL` y se encola para reintento manual.

## 8. Idempotencia y Concurrencia

- **Header**: `Idempotency-Key` obligatorio en `POST /reservations`.
- **Optimistic Locking**: Uso de `lock_version` para actualizaciones de estado.
- **Outbox Workers**: Mecanismo de bloqueo (`locked_by`) para procesamiento único.
