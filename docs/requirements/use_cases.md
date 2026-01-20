# Casos de Uso

## UC-001: Create Reservation

**Actor**: Cliente (Web/Mobile)
**Descripción**: Inicia el proceso de reserva bloqueando el precio y generando un código.
**Flujo Principal**:

1. Cliente envía detalles (Auto, Fechas, Datos Personales).
2. Sistema valida disponibilidad (Mock).
3. Sistema crea reserva en estado `DRAFT`.
4. Sistema retorna `reservation_code`.

## UC-002: Handle Webhook (Payment Confirmation)

**Actor**: Stripe (Sistema Externo)
**Descripción**: Confirma que el pago ha sido exitoso.
**Flujo Principal**:

1. Stripe envía evento `payment_intent.succeeded`.
2. Sistema valida firma.
3. Sistema actualiza reserva a `PAID`.
4. Sistema encola evento `CONFIRM_SUPPLIER` en Outbox (Transacción Atómica).

## UC-003: Process Outbox (Confirm Supplier)

**Actor**: Sistema (Worker)
**Descripción**: Procesa eventos pendientes para garantizar consistencia.
**Flujo Principal**:

1. Worker lee eventos `PENDING`.
2. Para cada evento `CONFIRM_SUPPLIER`:
   a. Obtiene datos de reserva.
   b. Llama a `SupplierGateway.confirm_booking`.
   c. Recibe `supplier_code`.
   d. Actualiza reserva a `CONFIRMED`.
   e. Marca evento como `PROCESSED`.
