# Listado de Requisitos para Matriz de Trazabilidad

**Fase:** A (Análisis)
**Destino:** Matriz de Trazabilidad (Excel)

## 1. Requisitos Funcionales (RF)

| ID | Descripción | Prioridad |
| :--- | :--- | :--- |
| **RF-001** | El sistema debe generar un **Código de Reserva Único** (8 caracteres) inmediatamente al crear la intención (Draft). Este código identificará la reserva durante todo su ciclo de vida. | Alta |
| **RF-002** | El sistema debe integrarse con Stripe para generar un PaymentIntent asociado a la reserva. | Alta |
| **RF-003** | El sistema debe procesar webhooks de Stripe para confirmar el pago de forma asíncrona. | Alta |
| **RF-004** | El sistema debe intentar confirmar la reserva con el Supplier Global (Adapter) tras el pago exitoso. | Alta |
| **RF-005** | **Regla de Fallo**: Si el Supplier falla tras el pago, el sistema debe confirmar con un código interno (`CONFIRMED_INTERNAL`) y no fallar la transacción. | Crítica |
| **RF-006** | El sistema debe permitir descargar el recibo solo si la reserva está confirmada (Supplier o Interna). | Media |
| **RF-007** | El sistema debe garantizar la idempotencia en la creación de reservas y procesamiento de pagos. | Alta |

## 2. Casos de Uso (CU)

| ID | Título | Actores | Precondición | Flujo Principal |
| :--- | :--- | :--- | :--- | :--- |
| **CU-01** | Crear Reserva | Cliente API | Token de Auth (si aplica), Datos válidos | 1. Valida datos. 2. Crea Reserva (Draft). 3. Retorna PaymentIntent. |
| **CU-02** | Confirmar Pago | Stripe (Webhook) | Reserva en `PENDING_PAYMENT` | 1. Recibe evento `succeeded`. 2. Actualiza a `PAID`. 3. Encola evento `BOOK_SUPPLIER`. |
| **CU-03** | Confirmar con Supplier (Happy Path) | Worker | Reserva `PAID`, Evento `BOOK_SUPPLIER` | 1. Llama Adapter. 2. Recibe OK. 3. Actualiza a `CONFIRMED`. |
| **CU-04** | Confirmar con Supplier (Fallback) | Worker | Reserva `PAID`, Error en Adapter | 1. Llama Adapter. 2. Recibe Error/Timeout. 3. Actualiza a `CONFIRMED_INTERNAL`. 4. Encola `RETRY`. |

## 3. Requisitos No Funcionales (RNF)

| ID | Descripción | Métrica |
| :--- | :--- | :--- |
| **RNF-001** | **Consistencia**: El estado del pago y la reserva deben ser consistentes eventualmente. | 100% consistencia tras procesamiento de Outbox. |
| **RNF-002** | **Disponibilidad**: El endpoint de creación de reserva debe responder en menos de 500ms. | < 500ms p95. |
| **RNF-003** | **Seguridad**: No almacenar datos sensibles de tarjetas (PCI DSS). | 0 datos de tarjeta en DB. |
| **RNF-004** | **Manejo de Tiempo**: El sistema debe operar internamente en UTC (EC2/DB) y convertir a hora local solo para visualización, siguiendo `spec/analisis_timezones.md`. | 100% fechas en UTC en DB. |
