# Arquitectura Fase B

## Capas y limites
- domain: entidades (Reservation, Payment, SupplierRequest, Contact, Driver), value objects (Money, DatetimeRange, ReservationCode), reglas de negocio; sin dependencias de frameworks.
- application: casos de uso (CreateReservationIntent, HandleStripeWebhook, ProcessOutboxBookSupplier, GetReceipt); orquestan flujos y dependen de puertos.
- infra: adaptadores de repositorios MySQL (SQLAlchemy async), gateways (Stripe, Supplier), outbox worker, lock handling; implementan puertos.
- api: FastAPI routers/schemas, validacion y DI; expone REST y encola tareas/outbox.

## Estructura de carpetas (sugerida)
app/
  domain/
    entities/
      reservation.py
      payment.py
      supplier_request.py
      contact.py
      driver.py
    value_objects/
      money.py
      reservation_code.py
      datetime_range.py
    errors.py
  application/
    use_cases/
      create_reservation_intent.py
      handle_stripe_webhook.py
      process_outbox_book_supplier.py
      get_receipt.py
    dtos/
      reservation_dto.py
      payment_dto.py
    interfaces/
      idempotency_repo.py
      reservation_repo.py
      contact_repo.py
      driver_repo.py
      payment_repo.py
      supplier_request_repo.py
      outbox_repo.py
      stripe_gateway.py
      supplier_gateway.py
      transaction_manager.py
      clock.py
      uuid_generator.py
  infrastructure/
    db/
      mysql_engine.py
      repositories/
        reservation_repo_sql.py
        payment_repo_sql.py
        idempotency_repo_sql.py
        supplier_request_repo_sql.py
        contact_repo_sql.py
        driver_repo_sql.py
        outbox_repo_sql.py
    gateways/
      stripe_gateway_impl.py
      supplier_gateway_impl.py
    messaging/
      outbox_worker.py
    services/
      clock_impl.py
      uuid_generator_impl.py
  api/
    routers/
      reservations.py
      webhooks.py
    schemas/
      reservations.py
      payments.py
      receipts.py
    dependencies.py
  main.py

## Casos de uso (puertos y reglas)
- CreateReservationIntent: valida payload y Idempotency-Key (IdempotencyRepo); verifica oficinas/supplier/producto en ReservationRepo; crea reservation PENDING/UNPAID, contactos, drivers en una transaccion (TransactionManager); publica outbox PaymentInitiated? (opcional) no dispara cobro; devuelve reservation_code y snapshot.
- HandleStripeWebhook: valida firma (StripeGateway); dedupe por stripe_event_id (PaymentRepo); actualiza Payment CAPTURED/FAILED y reservations.payment_status PAID/UNPAID con optimistic lock; en CAPTURED encola outbox event BookSupplierRequested; Conflict si evento ya procesado con otro estado definitivo.
- ProcessOutboxBookSupplier: outbox_repo.claim_next(status NEW|RETRY, locked_by, lock_expires_at); carga reservation+payment; crea reservation_supplier_requests attempt N status IN_PROGRESS; invoca SupplierGateway (idempotencia idem_key); actualiza supplier_request a SUCCESS/FAILED con payloads; si success => reservation.status CONFIRMED + supplier_reservation_code + supplier_confirmed_at; si fail => deja status ON_REQUEST y loguea error; marca outbox DONE o RETRY con backoff.
- GetReceipt: obtiene reservation por code, incluye contacts/drivers/payment/supplier_request; valida status CONFIRMED y supplier_reservation_code presente; si no, Conflict 409.

## Puertos clave
- IdempotencyRepo: get(scope, key) -> record; save(scope, key, request_hash, response_json, http_status, reference_reservation_id).
- ReservationRepo: create(reservation, contacts, drivers), get_by_code_for_update(code), update_status(code, status, lock_version), update_payment_status(code, payment_status, lock_version).
- PaymentRepo: create_pending(reservation_id, amount, currency, stripe_payment_intent_id), update_status(id, status, stripe_event_id, captured_at, provider_transaction_id), find_by_stripe_ids(pi_id, event_id).
- SupplierRequestRepo: create_in_progress(reservation_id, supplier_id, request_type, idem_key, payload), mark_success(id, response_payload), mark_failed(id, error_code, error_message, http_status, response_payload).
- OutboxRepo: enqueue(event_type, aggregate_type, aggregate_id, payload), claim_ready(limit, locked_by, now), mark_done(id), mark_retry(id, next_attempt_at, attempts).
- StripeGateway: verify_signature(payload, header), fetch_intent(data), capture/confirm intent if needed.
- SupplierGateway: book(reservation_snapshot, idem_key) -> {status, supplier_reservation_code, payload}.
- TransactionManager: async context to run functions with DB transaction.
- Clock/UUID: now(), generate_code() helpers deterministas para test.

## Resiliencia, concurrencia y datos
- Idempotencia estricta en creacion/pago/webhook; lock_version en updates de reservations; transacciones cortas al persistir (sin retener locks durante llamadas externas).
- Outbox claim usa locked_by + lock_expires_at; backoff exponencial por attempts; worker idempotente leyendo el payload de outbox.
- Supplier retries limitados: attempt++, idem_key estable para permitir dedupe en proveedor; marca FAILED y deja status ON_REQUEST en la reserva si agota reintentos.
- Validaciones de esquema alineadas a tablas (obligatoriedad de supplier_id, oficinas, montos, rental_days, etc.).
- Monitorear uq_payments_provider_tx y uq_payments_stripe_event para detectar anomalias; alertar si se intenta capturar pago ya CAPTURED o FAILED.

## DI y runtime
- api/dependencies.py arma las instancias de repositorios, gateways y clock/uuid; inyecta casos de uso en routers.
- main.py configura FastAPI, middlewares de request-id y logging estructurado.
- outbox_worker corre en proceso separado o BackgroundTasks con leases cortos; Stripe webhook endpoint debe ser publico y validar firma.

## Observabilidad
- Logs estructurados con reservation_code, stripe_payment_intent_id, stripe_event_id, idem_key, supplier_id, outbox_event_id, attempt.
- Metrics: contador de pagos capturados/fallidos, supplier success/fail, latencias de Stripe y suppliers, reintentos de outbox, colas pendientes.
- Tracing: spans por request HTTP, webhook, outbox job, llamada a supplier.
