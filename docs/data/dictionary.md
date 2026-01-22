# Diccionario de Datos

## Tabla: `reservations`

Almacena la información central de las reservas de autos.

| Columna                     | Tipo          | Constraints             | Descripción                                      |
| :-------------------------- | :------------ | :---------------------- | :----------------------------------------------- |
| `id`                        | Integer       | PK, Auto-inc            | Identificador interno.                           |
| `reservation_code`          | String(50)    | Unique, Index, Not Null | Código público de la reserva (ej. RES-ABC12345). |
| `supplier_id`               | Integer       | Not Null                | ID del proveedor (FK -> `suppliers`).            |
| `country_code`              | String(3)     | Not Null                | Código de país ISO.                              |
| `pickup_office_id`          | Integer       | Not Null                | ID de la oficina de entrega (FK -> `offices`).   |
| `dropoff_office_id`         | Integer       | Not Null                | ID de la oficina de devolución (FK -> `offices`).|
| `car_category_id`           | Integer       | Not Null                | ID de la categoría (FK -> `car_categories`).     |
| `supplier_car_product_id`   | Integer       | Nullable                | ID del producto específico del proveedor.        |
| `acriss_code`               | String(10)    | Nullable                | Código ACRISS del vehículo (ej. CDMR).           |
| `pickup_datetime`           | DateTime      | Not Null                | Fecha y hora de entrega.                         |
| `dropoff_datetime`          | DateTime      | Not Null                | Fecha y hora de devolución.                      |
| `rental_days`               | Integer       | Not Null                | Número de días de renta.                         |
| `public_price_total`        | Decimal(12,2) | Not Null                | Precio público total.                            |
| `supplier_cost_total`       | Decimal(12,2) | Not Null                | Costo del proveedor total.                       |
| `currency_code`             | String(3)     | Not Null                | Código de moneda ISO 4217.                       |
| `status`                    | String(32)    | Index, Not Null         | Estado: DRAFT, PAID, CONFIRMED, etc.             |
| `payment_status`            | String(32)    | Not Null                | Estado del pago (ej. 'PAID').                    |
| `sales_channel_id`          | Integer       | Not Null                | ID del canal de venta (FK -> `sales_channels`).  |
| `affiliate_id`              | Integer       | Nullable                | ID del afiliado (si aplica).                     |
| `supplier_reservation_code` | String(64)    | Nullable                | Código de confirmación del proveedor externo.    |
| `lock_version`              | Integer       | Default 0               | Control de concurrencia optimista.               |

## Tabla: `reservation_contacts`

Detalle de contacto del titular de la reserva.

| Columna            | Tipo         | Constraints  | Descripción                               |
| :----------------- | :----------- | :----------- | :---------------------------------------- |
| `id`               | Integer      | PK, Auto-inc | Identificador interno.                    |
| `reservation_id`   | Integer      | Not Null     | FK -> `reservations`.                     |
| `reservation_code` | String(50)   | Nullable     | Código de reserva (denormalizado).        |
| `contact_type`     | String(20)   | Not Null     | Tipo: BOOKER, EMERGENCY.                  |
| `full_name`        | String(255)  | Not Null     | Nombre completo.                          |
| `email`            | String(255)  | Not Null     | Correo electrónico.                       |
| `phone`            | String(50)   | Nullable     | Teléfono de contacto.                     |

## Tabla: `reservation_drivers`

Información de los conductores asociados a la reserva.

| Columna                 | Tipo         | Constraints  | Descripción                               |
| :---------------------- | :----------- | :----------- | :---------------------------------------- |
| `id`                    | Integer      | PK, Auto-inc | Identificador interno.                    |
| `reservation_id`        | Integer      | Not Null     | FK -> `reservations`.                     |
| `is_primary_driver`     | Integer      | Not Null     | 1 si es el conductor principal, 0 si no.  |
| `first_name`            | String(150)  | Not Null     | Nombre(s).                                |
| `last_name`             | String(150)  | Not Null     | Apellido(s).                              |
| `date_of_birth`         | String(20)   | Nullable     | Fecha de nacimiento.                      |
| `driver_license_number` | String(100)  | Nullable     | Número de licencia.                       |

## Tabla: `outbox_events`

Cola de eventos transaccionales para garantizar consistencia eventual (Transactional Outbox Pattern).

| Columna           | Tipo       | Constraints     | Descripción                               |
| :---------------- | :--------- | :-------------- | :---------------------------------------- |
| `id`              | Integer    | PK, Auto-inc    | Identificador del evento.                 |
| `event_type`      | String(64) | Not Null        | Tipo de evento (ej. 'CONFIRM_SUPPLIER').  |
| `aggregate_type`  | String(32) | Not Null        | Tipo de agregado (ej. 'RESERVATION').     |
| `aggregate_id`    | Integer    | Nullable        | ID del agregado relacionado.              |
| `aggregate_code`  | String(50) | Nullable        | Código público del agregado.              |
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

---

## Tablas de Referencia / Integración Legacy

Estas tablas son utilizadas para validar datos maestros y mapear códigos con el sistema legado.

### Tabla: `suppliers`
Maestro de proveedores (Hertz, Avis, Europcar, etc.).
- `id`: PK
- `name`: Nombre del proveedor.
- `code`: Código interno.
- `is_active`: Estado.

### Tabla: `offices`
Maestro de oficinas de renta.
- `id`: PK
- `name`: Nombre de la oficina.
- `code`: Código de la oficina (ej. 'CUN', 'MEX1').
- `supplier_id`: FK -> `suppliers`.
- `country_code`: Código país.

### Tabla: `car_categories`
Categorías de vehículos (Grupos).
- `id`: PK
- `name`: Nombre descriptivo (ej. 'Economy', 'Compact').
- `code`: Código interno.

### Tabla: `supplier_car_products`
Mapeo específico de productos por proveedor.
- `id`: PK
- `supplier_id`: FK -> `suppliers`.
- `car_category_id`: FK -> `car_categories`.
- `external_code`: Código que usa el proveedor en su API (SIPP o RateCode).

### Tabla: `reservation_supplier_requests`
Log de auditoría de las peticiones HTTP/SOAP enviadas a los proveedores.
- `id`: PK
- `reservation_id`: FK -> `reservations`.
- `request_type`: Tipo (BOOK, CANCEL).
- `request_payload`: JSON enviado.
- `response_payload`: JSON recibido.
- `status`: Estado de la petición (SUCCESS, FAILED).
- `http_status`: Código HTTP.