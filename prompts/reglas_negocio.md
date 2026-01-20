# Reglas de Negocio: Flujo "Crear Reserva y Cobro"

**Alcance Estricto**: Creación de Reserva y Procesamiento de Pago.
**Exclusiones**: No Auth, No Cancelación, No Disponibilidad.

## A. Identificación y Generación de Código
1.  **Código Único Inmediato**: Al recibir la solicitud, se debe generar un `reservation_code` único (8 caracteres alfanuméricos) **inmediatamente**. Este código identificará la transacción en Stripe y con el Supplier.
2.  **Supplier y Oficinas**:
    - `supplier_id` es obligatorio.
    - `pickup_office_id` y `dropoff_office_id` deben pertenecer al mismo supplier.
    - El backend debe resolver `office_code` a `office_id` si el frontend envía códigos.

## B. Vehículo y Categoría
1.  **Categoría Obligatoria**: `car_category_id` es el mínimo requerido.
2.  **Mapeo ACRISS**: Si se recibe un código ACRISS, el Adapter debe resolverlo a la categoría interna correspondiente.

## C. Fechas y Validación
1.  **Consistencia Temporal**: `pickup_datetime` < `dropoff_datetime`.
2.  **Antelación Mínima**: `pickup_datetime` debe ser al menos X horas (configuración) mayor a `now()`.
3.  **Timezones y Horarios Locales**:
    - **Input**: El frontend envía fechas en formato ISO 8601 con Timezone (ej. `2026-02-15T10:00:00-03:00` para ARG).
    - **Almacenamiento**: La BD guarda en **UTC** (`pickup_datetime`, `dropoff_datetime`).
    - **Lógica**: Se debe persistir el `timezone_offset` o el ID de zona horaria de la oficina (`America/Argentina/Buenos_Aires`) para reconstruir la hora local exacta en recibos y correos.
    - **Validación**: La validación de "horario de apertura" se hace convirtiendo UTC -> Hora Local de la Oficina.

## D. Montos y Moneda
1.  **Moneda**: `currency_code` es obligatorio y debe coincidir con la configuración del Supplier (o aplicar conversión).
2.  **Total**: `public_price_total` debe ser mayor a 0.

## E. Máquina de Estados (Alineada con Orquestador)
La tabla `reservations` usa los campos `status` y `payment_status`.

| Paso | Estado Reserva (`status`) | Estado Pago (`payment_status`) | Descripción |
| :--- | :--- | :--- | :--- |
| 1. Creación | `DRAFT` | `PENDING` | Reserva creada, esperando pago. |
| 2. Checkout | `PENDING_PAYMENT` | `PENDING` | PaymentIntent generado. |
| 3. Pago OK | `PENDING_SUPPLIER` | `PAID` | Webhook recibido. Inicia proceso con Supplier. |
| 4. Confirmación | `CONFIRMED` | `PAID` | Supplier confirmó con código externo. |
| 5. Fallback | `CONFIRMED_INTERNAL` | `PAID` | Supplier falló. Confirmación interna. |

**Regla de Oro**: Una vez que `payment_status` es `PAID`, la reserva **NUNCA** se cancela automáticamente por error técnico. Pasa a `CONFIRMED_INTERNAL`.

## F. Pago con Stripe
1.  **Idempotencia**: Usar `stripe_event_id` para evitar procesar el mismo webhook dos veces.
2.  **Single Source of Truth**: El estado `PAID` solo se establece tras recibir `payment_intent.succeeded`.

## G. Integración con Supplier (Globales)
1.  **Patrón Adapter**: Usar adaptadores específicos (Hertz, Budget, etc.) para normalizar Request/Response.
2.  **Auditoría**: Registrar TODO intento en `reservation_supplier_requests` (Payload JSON).
3.  **Manejo de Fallos (Fallback)**:
    - Si el Adapter retorna error, timeout o rechazo:
    - **NO** fallar la transacción.
    - **NO** reembolsar automáticamente.
    - **ACCIÓN**: Marcar `status = CONFIRMED_INTERNAL`.
    - **ACCIÓN**: Encolar evento `RETRY_SUPPLIER_BOOKING`.
    - **Último Recurso**: Si la gestión manual falla, el Sistema de Cancelaciones moverá el saldo a **Monedero**.

## H. Idempotencia del Endpoint
1.  **Header**: `Idempotency-Key` es obligatorio en `POST /reservations`.
2.  **Comportamiento**: Si la key existe, retornar la respuesta original sin crear duplicados en BD.

## I. Concurrencia
1.  **Optimistic Locking**: Usar `lock_version` para toda actualización de estado.
2.  **Outbox Workers**: Usar `locked_by` y `lock_expires_at` para asegurar que solo un worker procese el evento de confirmación.
