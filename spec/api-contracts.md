# Especificación de Contratos de API y Estados

**Versión:** 1.0
**Estado:** DRAFT
**Fecha:** 2026-01-16

## 1. Endpoints Definidos

| Método | Endpoint | Descripción |
| :--- | :--- | :--- |
| `POST` | `/v1/reservations` | Crea una intención de reserva (Draft) y retorna parámetros para pago. |
| `POST` | `/v1/webhooks/stripe` | Procesa eventos de pago asíncronos (Succeeded/Failed). |
| `GET` | `/v1/reservations/{code}/receipt` | Obtiene el recibo de la reserva (Solo CONFIRMED o CONFIRMED_INTERNAL). |

---

## 2. Máquina de Estados Combinada

La reserva tiene un ciclo de vida crítico que combina el estado del pago y la confirmación del proveedor.

| Estado Reserva (`status`) | Estado Pago (`payment_status`) | Descripción | Transición Siguiente |
| :--- | :--- | :--- | :--- |
| `DRAFT` | `PENDING` | Reserva creada, esperando inicio de pago. | -> `PENDING_PAYMENT` |
| `PENDING_PAYMENT` | `PENDING` | Intent de pago creado en Stripe. Cliente en checkout. | -> `PAID` o `CANCELLED` |
| `PAID` | `PAID` | Pago exitoso confirmado por Webhook. **Punto de no retorno**. | -> `PENDING_SUPPLIER` |
| `PENDING_SUPPLIER` | `PAID` | Worker intentando confirmar con Hertz/Budget/etc. | -> `CONFIRMED` o `CONFIRMED_INTERNAL` |
| `CONFIRMED` | `PAID` | **Happy Path**. Proveedor confirmó. Tenemos `supplier_reservation_code`. | Fin del flujo. |
| `CONFIRMED_INTERNAL` | `PAID` | **Fallback**. Proveedor falló/timeout. Confirmamos con nuestro código. | Requiere intervención manual/reintento. |

---

## 3. Contratos JSON (Request/Response)

### 3.1. Crear Reserva (`POST /v1/reservations`)

**Request:**
```json
{
  "supplier_id": 101,
  "car_category_id": 5,
  "pickup_office_id": 20,
  "dropoff_office_id": 20,
  "pickup_datetime": "2026-02-15T10:00:00-03:00", // ISO 8601 con Offset (ARG)
  "dropoff_datetime": "2026-02-18T10:00:00-03:00",
  "currency_code": "USD",
  "customer": {
    "first_name": "Juan",
    "last_name": "Perez",
    "email": "juan.perez@example.com",
    "phone": "+525512345678"
  },
  "driver": {
    "is_primary": true,
    "first_name": "Juan",
    "last_name": "Perez",
    "age": 30
  },
  "sales_channel_id": 1,
  "idempotency_key": "uuid-v4-unique-per-attempt"
}
```

**Response (201 Created):**
```json
{
  "reservation_code": "ABC12345", // Nuestro código interno único (Generado siempre)
  "status": "DRAFT",
  "payment_info": {
    "client_secret": "pi_12345_secret_67890",
    "public_key": "pk_test_..."
  },
  "expiration_at": "2026-01-16T10:30:00Z"
}
```

### 3.2. Webhook Stripe (`POST /v1/webhooks/stripe`)

**Request (Standard Stripe Payload):**
```json
{
  "id": "evt_123456789",
  "type": "payment_intent.succeeded",
  "data": {
    "object": {
      "id": "pi_123456789",
      "amount": 15000,
      "currency": "usd",
      "metadata": {
        "reservation_code": "ABC12345"
      }
    }
  }
}
```

**Response (200 OK):**
```json
{
  "received": true
}
```

### 3.3. Obtener Recibo (`GET /v1/reservations/{code}/receipt`)

**Response (200 OK):**
```json
{
  "reservation_code": "ABC12345",
  "status": "CONFIRMED",
  "supplier": {
    "name": "Hertz",
    "confirmation_code": "H123-999" 
  },
  "vehicle": {
    "category": "Compact",
    "description": "Nissan Versa or similar"
  },
  "dates": {
    "pickup": "2026-02-15T10:00:00Z",
    "dropoff": "2026-02-18T10:00:00Z"
  },
  "payment": {
    "total": 150.00,
    "currency": "USD",
    "status": "PAID"
  },
  "driver": {
    "full_name": "Juan Perez"
  }
}
```
*Nota: Si el status es `CONFIRMED_INTERNAL`, el campo `supplier.confirmation_code` puede ser nulo o indicar "PENDING_ASSIGNMENT".*

---

## 4. Matriz de Idempotencia

| Scope | Idempotency Key Source | Acción |
| :--- | :--- | :--- |
| `RESERVATION_CREATE` | Header `Idempotency-Key` (Client) | Retornar misma reserva sin recrear. |
| `STRIPE_WEBHOOK` | `event.id` (Stripe Body) | Ignorar evento ya procesado. |
| `SUPPLIER_BOOKING` | `reservation_code` + `attempt_id` | Evitar doble booking en Hertz/Budget. |

---

## 5. Reglas de Negocio Críticas (Validación)

1.  **Validación de Fechas**: `pickup_datetime` > `now() + 2h` (Mínimo tiempo de antelación). `dropoff` > `pickup`.
2.  **Edad del Conductor**: Validar edad mínima según categoría de auto (Regla general: 21+).
3.  **Moneda**: Validar que `currency_code` coincida con la configuración del `supplier` o aplicar conversión.
