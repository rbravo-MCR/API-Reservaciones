# ADR 002: Transactional Outbox Pattern

## Status

Accepted

## Context

When a reservation is paid (via Stripe Webhook), we need to update the local database status to `PAID` and trigger a call to the external supplier to confirm the booking. If we update the DB and then call the supplier (or publish a message) and the process fails in between, we end up in an inconsistent state (Paid but not Confirmed). Distributed transactions (2PC) are complex and not supported by many APIs.

## Decision

We will use the **Transactional Outbox Pattern**.

1.  **Atomic Transaction**: When processing the payment webhook, we update the `reservations` table AND insert a record into an `outbox_events` table in the **same local database transaction**.
2.  **Asynchronous Processing**: A background process (Worker) polls the `outbox_events` table for `PENDING` events.
3.  **At-Least-Once Delivery**: The worker processes the event (calls Supplier) and marks it as `PROCESSED`. If it fails, it retries. This implies the consumer (Supplier Gateway) must be idempotent.

## Consequences

### Positive

- **Consistency**: Guarantees that if the reservation is paid locally, the confirmation event will eventually be processed.
- **Resilience**: The system can tolerate temporary failures of the external supplier.

### Negative

- **Latency**: There is a delay between payment and confirmation (Eventual Consistency).
- **Complexity**: Requires implementing a background worker and handling retries/failures.
