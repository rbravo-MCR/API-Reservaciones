# Diccionario de Datos

## Tabla: `reservations`

Almacena la información central de las reservas de autos.

| Columna                     | Tipo          | Constraints             | Descripción                                      |
| :-------------------------- | :------------ | :---------------------- | :----------------------------------------------- |
| `id`                        | Integer       | PK, Auto-inc            | Identificador interno.                           |
| `reservation_code`          | String(50)    | Unique, Index, Not Null | Código público de la reserva (ej. RES-ABC12345). |
| `supplier_id`               | Integer       | Not Null                | ID del proveedor.                                |
| `country_code`              | String(3)     | Not Null                | Código de país ISO.                              |
| `pickup_office_id`          | Integer       | Not Null                | ID de la oficina de entrega.                     |
| `dropoff_office_id`         | Integer       | Not Null                | ID de la oficina de devolución.                  |
| `car_category_id`           | Integer       | Not Null                | ID de la categoría de auto.                      |
| `acriss_code`               | String(10)    | Nullable                | Código ACRISS del vehículo.                      |
| `pickup_datetime`           | DateTime      | Not Null                | Fecha y hora de entrega.                         |
| `dropoff_datetime`          | DateTime      | Not Null                | Fecha y hora de devolución.                      |
| `rental_days`               | Integer       | Not Null                | Número de días de renta.                         |
| `public_price_total`        | Decimal(12,2) | Not Null                | Precio público total.                            |
| `supplier_cost_total`       | Decimal(12,2) | Not Null                | Costo del proveedor total.                       |
| `currency_code`             | String(3)     | Not Null                | Código de moneda ISO 4217.                       |
| `status`                    | String(32)    | Index, Not Null         | Estado: DRAFT, PAID, CONFIRMED, etc.             |
| `payment_status`            | String(32)    | Not Null                | Estado del pago (ej. 'PAID').                    |
| `sales_channel_id`          | Integer       | Not Null                | ID del canal de venta.                           |
| `supplier_reservation_code` | String(64)    | Nullable                | Código de confirmación del proveedor externo.    |
| `lock_version`              | Integer       | Default 0               | Control de concurrencia optimista.               |

## Tabla: `outbox_events`

Cola de eventos transaccionales para garantizar consistencia eventual.

| Columna           | Tipo       | Constraints     | Descripción                               |
| :---------------- | :--------- | :-------------- | :---------------------------------------- |
| `id`              | Integer    | PK, Auto-inc    | Identificador del evento.                 |
| `event_type`      | String(64) | Not Null        | Tipo de evento (ej. 'CONFIRM_SUPPLIER').  |
| `aggregate_type`  | String(32) | Not Null        | Tipo de agregado (ej. 'RESERVATION').     |
| `aggregate_id`    | Integer    | Nullable        | ID del agregado relacionado.              |
| `payload`         | JSON       | Not Null        | Datos necesarios para procesar el evento. |
| `status`          | String(16) | Index, Not Null | Estado: NEW, PROCESSED, FAILED.           |
| `attempts`        | Integer    | Default 0       | Número de intentos de procesamiento.      |
| `next_attempt_at` | DateTime   | Nullable        | Fecha programada para el próximo intento. |

## Tabla: `payments`

Almacena los registros de pagos para asegurar idempotencia y trazabilidad financiera.

| Columna                    | Tipo          | Constraints  | Descripción                       |
| :------------------------- | :------------ | :----------- | :-------------------------------- |
| `id`                       | Integer       | PK, Auto-inc | Identificador interno.            |
| `reservation_id`           | Integer       | Not Null     | ID de la reserva asociada.        |
| `provider`                 | String(100)   | Not Null     | Proveedor de pago (ej. 'STRIPE'). |
| `status`                   | String(32)    | Not Null     | Estado del pago (ej. 'CAPTURED'). |
| `amount`                   | Decimal(12,2) | Not Null     | Monto cobrado.                    |
| `currency_code`            | String(3)     | Not Null     | Código de moneda.                 |
| `stripe_payment_intent_id` | String(64)    | Nullable     | ID del Payment Intent de Stripe.  |
| `stripe_charge_id`         | String(64)    | Nullable     | ID del Charge de Stripe.          |

## Tabla: `idempotency_keys`

Control de idempotencia para peticiones API.

| Columna         | Tipo        | Constraints  | Descripción                                    |
| :-------------- | :---------- | :----------- | :--------------------------------------------- |
| `id`            | Integer     | PK, Auto-inc | Identificador interno.                         |
| `scope`         | String(32)  | Not Null     | Ámbito de la clave (ej. 'RESERVATION_CREATE'). |
| `idem_key`      | String(128) | Not Null     | Clave de idempotencia enviada por el cliente.  |
| `request_hash`  | String(64)  | Not Null     | Hash del payload para validar cambios.         |
| `response_json` | JSON        | Nullable     | Respuesta cacheada.                            |
| `http_status`   | Integer     | Nullable     | Código HTTP cacheado.                          |
