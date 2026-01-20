# Matriz de Trazabilidad - Reservation Backend

| ID Requisito | Descripción                    | Caso de Uso                | Componente (Código)                                         | Test Case              | Estado  |
| :----------- | :----------------------------- | :------------------------- | :---------------------------------------------------------- | :--------------------- | :------ |
| **REQ-001**  | Crear Reserva (Draft)          | UC-001: Create Reservation | `CreateReservationUseCase`, `POST /reservations`            | TC-001, TC-003, TC-005 | ✅ Impl |
| **REQ-002**  | Procesar Pago Stripe           | UC-002: Handle Webhook     | `HandleStripeWebhookUseCase`, `POST /webhooks/stripe`       | TC-001, TC-004         | ✅ Impl |
| **REQ-003**  | Consistencia Eventual (Outbox) | UC-002, UC-003             | `ReservationRepository.mark_as_paid...`, `OutboxEventModel` | TC-001, TC-002         | ✅ Impl |
| **REQ-004**  | Confirmar con Proveedor        | UC-003: Process Outbox     | `ProcessOutboxUseCase`, `SupplierGateway`                   | TC-001, TC-002         | ✅ Impl |
| **REQ-005**  | Idempotencia en Webhook        | UC-002                     | `HandleStripeWebhookUseCase`, `PaymentModel` (Unique)       | TC-004                 | ✅ Impl |
| **REQ-006**  | Resiliencia (Retry)            | UC-003                     | `ProcessOutboxUseCase` (Retry Logic)                        | TC-002                 | ✅ Impl |
| **REQ-007**  | Protección PII                 | N/A                        | `ReservationModel` (Aligned with Production)                | N/A                    | ✅ Impl |
| **REQ-008**  | Idempotencia en API            | UC-001                     | `IdempotencyMiddleware` / `CreateReservationUseCase`        | TC-003                 | ✅ Impl |
