# Diccionario de Datos

## Tabla: `reservations`

Almacena la información central de las reservas de autos.

| Columna                     | Tipo          | Constraints             | Descripción                                   |
| :-------------------------- | :------------ | :---------------------- | :-------------------------------------------- |
| `id`                        | Integer       | PK, Auto-inc            | Identificador interno.                        |
| `reservation_code`          | String(8)     | Unique, Index, Not Null | Código público de la reserva (ej. ABC12345).  |
| `supplier_id`               | Integer       | FK, Not Null            | ID del proveedor (referencia a `suppliers`).  |
| `pickup_office_id`          | Integer       | FK, Not Null            | ID de la oficina de entrega.                  |
| `dropoff_office_id`         | Integer       | FK, Not Null            | ID de la oficina de devolución.               |
| `car_category_id`           | Integer       | FK, Not Null            | ID de la categoría de auto.                   |
| `sales_channel_id`          | Integer       | FK, Not Null            | ID del canal de venta.                        |
| `pickup_datetime`           | DateTime      | Not Null                | Fecha y hora de entrega.                      |
| `dropoff_datetime`          | DateTime      | Not Null                | Fecha y hora de devolución.                   |
| `rental_days`               | Integer       | Not Null                | Número de días de renta.                      |
| `public_price_total`        | Decimal(12,2) | Not Null                | Precio público total.                         |
| `supplier_cost_total`       | Decimal(12,2) | Not Null                | Costo del proveedor total.                    |
| `currency_code`             | String(3)     | Default 'USD'           | Código de moneda ISO 4217.                    |
| `status`                    | Enum          | Index, Not Null         | Estado: DRAFT, PAID, CONFIRMED, etc.          |
| `payment_status`            | String(20)    | Nullable                | Estado del pago (ej. 'PAID').                 |
| `supplier_reservation_code` | String(64)    | Nullable                | Código de confirmación del proveedor externo. |
| `lock_version`              | Integer       | Default 1               | Control de concurrencia optimista.            |
| `created_at`                | DateTime      | Index, UTC              | Fecha de creación.                            |
| `updated_at`                | DateTime      | UTC                     | Fecha de última actualización.                |

## Tabla: `outbox_events`

Cola de eventos transaccionales para garantizar consistencia eventual.

| Columna           | Tipo       | Constraints     | Descripción                               |
| :---------------- | :--------- | :-------------- | :---------------------------------------- |
| `id`              | Integer    | PK, Auto-inc    | Identificador del evento.                 |
| `event_type`      | String(64) | Not Null        | Tipo de evento (ej. 'CONFIRM_SUPPLIER').  |
| `aggregate_type`  | String(32) | Not Null        | Tipo de agregado (ej. 'RESERVATION').     |
| `aggregate_id`    | Integer    | Not Null        | ID del agregado relacionado.              |
| `payload`         | JSON       | Not Null        | Datos necesarios para procesar el evento. |
| `status`          | Enum       | Index, Not Null | Estado: PENDING, PROCESSED, FAILED.       |
| `attempts`        | Integer    | Default 0       | Número de intentos de procesamiento.      |
| `created_at`      | DateTime   | UTC             | Fecha de creación.                        |
| `updated_at`      | DateTime   | UTC             | Fecha de última actualización.            |
| `next_attempt_at` | DateTime   | Nullable, UTC   | Fecha programada para el próximo intento. |

## Tabla: `payments`

Almacena los registros de pagos para asegurar idempotencia y trazabilidad financiera.

| Columna                   | Tipo          | Constraints      | Descripción                       |
| :------------------------ | :------------ | :--------------- | :-------------------------------- |
| `id`                      | Integer       | PK, Auto-inc     | Identificador interno.            |
| `reservation_id`          | Integer       | FK, Not Null     | ID de la reserva asociada.        |
| `provider`                | String(100)   | Not Null         | Proveedor de pago (ej. 'STRIPE'). |
| `provider_transaction_id` | String(255)   | Unique, Nullable | ID de transacción del proveedor.  |
| `amount`                  | Decimal(12,2) | Not Null         | Monto cobrado.                    |
| `currency_code`           | String(3)     | Not Null         | Código de moneda.                 |
| `status`                  | String(20)    | Not Null         | Estado del pago (ej. 'CAPTURED'). |
| `created_at`              | DateTime      | UTC              | Fecha de creación.                |
| `updated_at`              | DateTime      | UTC              | Fecha de última actualización.    |
