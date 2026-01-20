# Plan de Pruebas - Reservation Backend

Este documento describe la estrategia de pruebas para el sistema de reservas.

## 1. Objetivos de las Pruebas

- Validar el flujo end-to-end de creación de reserva y cobro.
- Asegurar la integridad de los datos y la consistencia eventual (Outbox).
- Verificar la resiliencia ante fallos de proveedores externos.
- Validar la idempotencia en endpoints y webhooks.

## 2. Tipos de Pruebas

### 2.1. Pruebas Unitarias

- Validación de lógica de negocio en Use Cases.
- Mapeo de datos en Adapters.
- Generación de códigos y validación de fechas.

### 2.2. Pruebas de Integración

- Interacción con la base de datos (MySQL/SQLite).
- Integración con Stripe (usando mocks o entorno de test).
- Comunicación con Gateways de proveedores.

### 2.3. Pruebas End-to-End (E2E)

- Flujo completo desde `POST /reservations` hasta la generación del recibo.
- Simulación de webhooks de Stripe.
- Procesamiento de eventos Outbox por el Worker.

## 3. Casos de Prueba (TC)

| ID         | Nombre                       | Descripción                                                                    | Requisito                 |
| :--------- | :--------------------------- | :----------------------------------------------------------------------------- | :------------------------ |
| **TC-001** | Happy Path E2E               | Flujo completo exitoso: Reserva -> Pago -> Confirmación Supplier -> Recibo.    | REQ-001, REQ-002, REQ-004 |
| **TC-002** | Fallo de Supplier (Fallback) | Pago exitoso pero el proveedor falla. Debe quedar en `CONFIRMED_INTERNAL`.     | REQ-004, REQ-006          |
| **TC-003** | Idempotencia de Reserva      | Intentar crear la misma reserva con la misma `Idempotency-Key`.                | REQ-001, REQ-008          |
| **TC-004** | Idempotencia de Webhook      | Procesar el mismo evento de Stripe dos veces.                                  | REQ-002, REQ-005          |
| **TC-005** | Validación de Fechas         | Intentar reservar con fecha de recogida en el pasado o posterior a la entrega. | REQ-001                   |

## 4. Herramientas

- **Framework**: pytest
- **Cliente HTTP**: httpx (AsyncClient)
- **Linter/Formatter**: ruff
- **Base de Datos**: MySQL (Prod/Dev) / SQLite (Test)

## 5. Ejecución de Pruebas

Para ejecutar las pruebas E2E:

```bash
python -m pytest tests/test_reservation_flow.py
```
