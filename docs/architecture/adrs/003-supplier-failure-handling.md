# ADR 003: Supplier Failure Handling

## Status

Accepted

## Context

External suppliers (Hertz, Budget) may experience downtime, timeouts (>30s), or return 5xx errors. Since we have already charged the customer (Stripe Payment Succeeded), we cannot simply fail the request or refund immediately without attempting recovery. We need a strategy to handle these failures while maintaining a good User Experience.

## Decision

We will implement a **"Confirm Internal, Retry External"** strategy.

1.  **Decoupling**: The confirmation process is already asynchronous (via Outbox).
2.  **Timeout/Error Handling**: If the Supplier Gateway times out or returns a 5xx error:
    - The Worker catches the exception.
    - **Action**:
      - Update Reservation Status to `CONFIRMED_INTERNAL`.
      - Increment `retry_count` on the Outbox Event.
      - Keep the event status as `PENDING` (or `RETRYING`).
3.  **User Communication**: The user receives a confirmation email with the _Internal_ Reservation Code immediately. The Supplier Code is added later when available.
4.  **Manual Intervention**: If retries are exhausted (e.g., > 5 attempts), the event moves to `FAILED` and triggers an alert for manual resolution (Support Team calls Supplier).

## Consequences

### Positive

- **Revenue Protection**: We don't lose the sale due to temporary supplier glitches.
- **UX**: User gets immediate confirmation and peace of mind.

### Negative

- **Operational Complexity**: Requires a manual process for "Dead Letter" events.
- **Risk**: Small risk of "Overbooking" if the supplier is truly sold out when we finally connect, requiring a manual refund/upgrade.
