# PRD: Vertical Slice - Reserva y Cobro

**Estado**: Aprobado
**Fecha**: 2026-01-19
**Autor**: PR Manager

## 1. Resumen Ejecutivo
Este slice implementa el flujo core del negocio: **Crear una Reserva, Cobrarla y Confirmarla con el Proveedor**.
El objetivo es maximizar la conversión y garantizar la integridad de los datos, manejando los fallos de proveedores externos sin afectar la experiencia del usuario (Estrategia de Fallback).

## 2. Alcance (In / Out)

### IN (Dentro del Alcance)
- Endpoint `POST /reservations`: Creación de reserva y generación de PaymentIntent.
- Endpoint `POST /webhooks/stripe`: Confirmación de pago asíncrona.
- Endpoint `GET /reservations/{code}/receipt`: Consulta de estado y recibo.
- **Integración Stripe**: Cobro en moneda del proveedor.
- **Integración Supplier**: Adaptador genérico (Simulado o Real) para confirmar reserva.
- **Resiliencia**: Manejo de `CONFIRMED_INTERNAL` si falla el supplier.
- **Auditoría**: Registro de requests/responses en `reservation_supplier_requests`.

### OUT (Fuera del Alcance)
- Autenticación de usuarios (Login/Registro).
- Búsqueda de disponibilidad (Se asume disponibilidad validada previamente).
- Cancelaciones y Reembolsos automáticos.
- Envío de Emails (Se hará en otro slice).

## 3. Criterios de Aceptación (User Stories)

### US-01: Crear Intención de Reserva
**Como** cliente,
**Quiero** reservar un auto seleccionando categoría y fechas,
**Para** asegurar mi movilidad en el destino.

**Criterios:**
- El sistema debe generar un `reservation_code` único de 8 caracteres inmediatamente.
- Debe retornar un `client_secret` de Stripe para el checkout en el frontend.
- El estado inicial de la reserva debe ser `DRAFT`.
- Debe validar que `pickup_datetime` sea al menos 2 horas en el futuro.

### US-02: Procesar Pago Exitoso
**Como** sistema,
**Quiero** recibir la confirmación de pago de Stripe,
**Para** proceder a reservar el auto con el proveedor.

**Criterios:**
- El webhook debe ser idempotente (usar `stripe_event_id`).
- Al recibir `payment_intent.succeeded`, el estado de pago debe pasar a `PAID`.
- El estado de la reserva debe pasar a `PENDING_SUPPLIER`.
- Debe disparar el proceso de confirmación con el proveedor (Worker/Outbox).

### US-03: Confirmación con Proveedor (Happy Path)
**Como** sistema,
**Quiero** confirmar la reserva con el proveedor global (Hertz, Budget),
**Para** obtener el código de confirmación real.

**Criterios:**
- El sistema debe enviar la solicitud al proveedor correspondiente.
- Si el proveedor responde OK, guardar `supplier_booking_code`.
- Cambiar estado a `CONFIRMED`.

### US-04: Manejo de Fallo de Proveedor (Fallback)
**Como** PR Manager,
**Quiero** que si el proveedor falla (timeout/error) después de cobrar, NO se cancele la reserva,
**Para** no perder la venta y gestionar la incidencia manualmente.

**Criterios:**
- Si el proveedor falla, cambiar estado a `CONFIRMED_INTERNAL`.
- **NO** reembolsar automáticamente.
- Registrar el error en logs de auditoría.

## 4. Métricas de Éxito
- **Tasa de Conversión**: % de Reservas DRAFT que terminan en CONFIRMED/CONFIRMED_INTERNAL.
- **Tasa de Fallo Supplier**: % de Reservas que terminan en CONFIRMED_INTERNAL.
- **Latencia API**: Tiempo de respuesta del `POST /reservations` < 500ms.
