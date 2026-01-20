-- Migration: add outbox_event locking/backoff fields
-- Date: 2026-01-15

ALTER TABLE outbox_events
  ADD COLUMN IF NOT EXISTS attempts INT NOT NULL DEFAULT 0 AFTER status,
  ADD COLUMN IF NOT EXISTS next_attempt_at DATETIME NULL AFTER attempts,
  ADD COLUMN IF NOT EXISTS locked_by VARCHAR(64) NULL AFTER next_attempt_at,
  ADD COLUMN IF NOT EXISTS locked_at DATETIME NULL AFTER locked_by,
  ADD COLUMN IF NOT EXISTS lock_expires_at DATETIME NULL AFTER locked_at,
  ADD COLUMN IF NOT EXISTS created_at DATETIME NULL AFTER payload,
  ADD COLUMN IF NOT EXISTS updated_at DATETIME NULL AFTER created_at;

-- Recommended indexes for worker claim/backoff (run once if not present)
CREATE INDEX idx_outbox_status_next ON outbox_events (status, next_attempt_at);
CREATE INDEX idx_outbox_worker_claim ON outbox_events (status, next_attempt_at, id);

-- Ensure lookup tables exist for validations/receipt lookups:
-- offices(id, code, name), suppliers(id, name), supplier_car_products(id, car_category_id, external_code).
