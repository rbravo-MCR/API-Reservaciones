-- Migration: add country_code and office codes to reservations
-- Date: 2026-01-15

ALTER TABLE reservations
  ADD COLUMN IF NOT EXISTS country_code CHAR(3) NOT NULL AFTER supplier_id,
  ADD COLUMN IF NOT EXISTS pickup_office_code VARCHAR(50) NULL AFTER pickup_office_id,
  ADD COLUMN IF NOT EXISTS dropoff_office_code VARCHAR(50) NULL AFTER dropoff_office_id;
