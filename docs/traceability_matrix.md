# Matriz de Trazabilidad - Reservation Backend

| ID Requisito | Descripción             | Caso de Uso    | Componente (Código)                                 | Test Case      | Estado  |
| :----------- | :---------------------- | :------------- | :-------------------------------------------------- | :------------- | :------ |
| ID Requisito | Descripción             | Caso de Uso    | Componente (Código)                                 | Test Case      | Estado  |
| :---         | :---                    | :---           | :---                                                | :---           | :---    |
| **REQ-001**  | Crear Reserva (Draft)   | UC-001         | `CreateReservationIntentUseCase`                    | TC-001, TC-003 | ✅ Impl |
| **REQ-002**  | Procesar Pago Stripe    | UC-002         | `HandleStripeWebhookUseCase`                        | TC-001, TC-004 | ✅ Impl |
| **REQ-003**  | Consistencia Eventual   | UC-002, UC-003 | `OutboxRepoSQL`, `ProcessOutboxBookSupplierUseCase` | TC-001         | ✅ Impl |
| **REQ-004**  | Confirmar con Proveedor | UC-003         | `SupplierGatewaySelector`, `SupplierGatewayHTTP`    | TC-001, TC-002 | ✅ Impl |
| **REQ-005**  | Idempotencia Webhook    | UC-002         | `PaymentRepoSQL` (Unique Constraint)                | TC-004         | ✅ Impl |
| **REQ-006**  | Resiliencia (Fallback)  | UC-003         | `ProcessOutboxBookSupplierUseCase`                  | TC-002         | ✅ Impl |
| **REQ-007**  | Protección PII          | N/A            | `ReservationModel`                                  | N/A            | ✅ Impl |
| **REQ-008**  | Idempotencia API        | UC-001         | `IdempotencyRepoSQL`                                | TC-003         | ✅ Impl |
| **REQ-009**  | Generación de Recibo    | UC-004         | `GetReceiptUseCase`, `ReceiptQuerySQL`              | TC-001         | ✅ Impl |
