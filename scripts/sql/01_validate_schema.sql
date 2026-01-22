-- ============================================================================
-- Script 01: Validación de Esquema de Base de Datos
-- Propósito: Verificar que todas las tablas requeridas existan con la estructura correcta
-- Uso: mysql -h <host> -u <user> -p <database> < 01_validate_schema.sql
-- ============================================================================

-- Verificar que la base de datos existe
SELECT DATABASE() AS current_database;

-- ============================================================================
-- 1. VERIFICAR EXISTENCIA DE TABLAS
-- ============================================================================
SELECT
    'TABLA: reservations' AS check_name,
    CASE
        WHEN COUNT(*) = 1 THEN '✓ EXISTS'
        ELSE '✗ MISSING'
    END AS status
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name = 'reservations'

UNION ALL

SELECT
    'TABLA: reservation_contacts' AS check_name,
    CASE
        WHEN COUNT(*) = 1 THEN '✓ EXISTS'
        ELSE '✗ MISSING'
    END AS status
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name = 'reservation_contacts'

UNION ALL

SELECT
    'TABLA: reservation_drivers' AS check_name,
    CASE
        WHEN COUNT(*) = 1 THEN '✓ EXISTS'
        ELSE '✗ MISSING'
    END AS status
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name = 'reservation_drivers'

UNION ALL

SELECT
    'TABLA: payments' AS check_name,
    CASE
        WHEN COUNT(*) = 1 THEN '✓ EXISTS'
        ELSE '✗ MISSING'
    END AS status
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name = 'payments'

UNION ALL

SELECT
    'TABLA: idempotency_keys' AS check_name,
    CASE
        WHEN COUNT(*) = 1 THEN '✓ EXISTS'
        ELSE '✗ MISSING'
    END AS status
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name = 'idempotency_keys'

UNION ALL

SELECT
    'TABLA: outbox_events' AS check_name,
    CASE
        WHEN COUNT(*) = 1 THEN '✓ EXISTS'
        ELSE '✗ MISSING'
    END AS status
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name = 'outbox_events'

UNION ALL

SELECT
    'TABLA: outbox_dead_letters' AS check_name,
    CASE
        WHEN COUNT(*) = 1 THEN '✓ EXISTS'
        ELSE '✗ MISSING (PROB-003 requerido)'
    END AS status
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name = 'outbox_dead_letters'

UNION ALL

SELECT
    'TABLA: reservation_supplier_requests' AS check_name,
    CASE
        WHEN COUNT(*) = 1 THEN '✓ EXISTS'
        ELSE '✗ MISSING'
    END AS status
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name = 'reservation_supplier_requests'

UNION ALL

SELECT
    'TABLA: suppliers' AS check_name,
    CASE
        WHEN COUNT(*) = 1 THEN '✓ EXISTS'
        ELSE '✗ MISSING'
    END AS status
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name = 'suppliers'

UNION ALL

SELECT
    'TABLA: offices' AS check_name,
    CASE
        WHEN COUNT(*) = 1 THEN '✓ EXISTS'
        ELSE '✗ MISSING'
    END AS status
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name = 'offices'

UNION ALL

SELECT
    'TABLA: car_categories' AS check_name,
    CASE
        WHEN COUNT(*) = 1 THEN '✓ EXISTS'
        ELSE '✗ MISSING'
    END AS status
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name = 'car_categories'

UNION ALL

SELECT
    'TABLA: sales_channels' AS check_name,
    CASE
        WHEN COUNT(*) = 1 THEN '✓ EXISTS'
        ELSE '✗ MISSING'
    END AS status
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name = 'sales_channels'

UNION ALL

SELECT
    'TABLA: supplier_car_products' AS check_name,
    CASE
        WHEN COUNT(*) = 1 THEN '✓ EXISTS'
        ELSE '✗ MISSING'
    END AS status
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name = 'supplier_car_products';

-- ============================================================================
-- 2. VERIFICAR COLUMNAS CRÍTICAS DE RESERVATIONS
-- ============================================================================
SELECT
    'COLUMNA: reservations.lock_version' AS check_name,
    CASE
        WHEN COUNT(*) = 1 THEN '✓ EXISTS (Optimistic Locking)'
        ELSE '✗ MISSING - CRÍTICO para concurrencia'
    END AS status
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name = 'reservations'
  AND column_name = 'lock_version'

UNION ALL

SELECT
    'COLUMNA: reservations.reservation_code (UNIQUE)' AS check_name,
    CASE
        WHEN COUNT(*) = 1 THEN '✓ UNIQUE constraint exists'
        ELSE '✗ MISSING UNIQUE constraint'
    END AS status
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name = 'reservations'
  AND column_name = 'reservation_code'
  AND non_unique = 0;

-- ============================================================================
-- 3. VERIFICAR ÍNDICES CRÍTICOS
-- ============================================================================
SELECT
    'ÍNDICE: idempotency_keys unique (scope, idem_key)' AS check_name,
    CASE
        WHEN COUNT(*) >= 1 THEN '✓ EXISTS (Idempotency protection)'
        ELSE '✗ MISSING - CRÍTICO para PROB-001'
    END AS status
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name = 'idempotency_keys'
  AND column_name IN ('scope', 'idem_key')
  AND non_unique = 0;

-- ============================================================================
-- 4. VERIFICAR COLUMNAS DE OUTBOX_EVENTS (para retry de deadlocks)
-- ============================================================================
SELECT
    'COLUMNA: outbox_events.locked_by' AS check_name,
    CASE
        WHEN COUNT(*) = 1 THEN '✓ EXISTS (Distributed locking)'
        ELSE '✗ MISSING'
    END AS status
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name = 'outbox_events'
  AND column_name = 'locked_by'

UNION ALL

SELECT
    'COLUMNA: outbox_events.lock_expires_at' AS check_name,
    CASE
        WHEN COUNT(*) = 1 THEN '✓ EXISTS (Lock TTL)'
        ELSE '✗ MISSING'
    END AS status
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name = 'outbox_events'
  AND column_name = 'lock_expires_at';

-- ============================================================================
-- 5. VERIFICAR COLUMNAS DE DLQ (PROB-003)
-- ============================================================================
SELECT
    'COLUMNA: outbox_dead_letters.error_code' AS check_name,
    CASE
        WHEN COUNT(*) = 1 THEN '✓ EXISTS (Error tracking)'
        ELSE '✗ MISSING - Requerido para DLQ'
    END AS status
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name = 'outbox_dead_letters'
  AND column_name = 'error_code'

UNION ALL

SELECT
    'COLUMNA: outbox_dead_letters.moved_at' AS check_name,
    CASE
        WHEN COUNT(*) = 1 THEN '✓ EXISTS (DLQ timestamp)'
        ELSE '✗ MISSING'
    END AS status
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name = 'outbox_dead_letters'
  AND column_name = 'moved_at';

-- ============================================================================
-- 6. RESUMEN DE VALIDACIÓN
-- ============================================================================
SELECT '============ RESUMEN DE VALIDACIÓN ============' AS summary;

SELECT
    COUNT(*) AS total_tables,
    SUM(CASE WHEN table_name IN (
        'reservations', 'reservation_contacts', 'reservation_drivers',
        'payments', 'idempotency_keys', 'outbox_events',
        'outbox_dead_letters', 'reservation_supplier_requests',
        'suppliers', 'offices', 'car_categories', 'sales_channels',
        'supplier_car_products'
    ) THEN 1 ELSE 0 END) AS required_tables_found,
    13 AS required_tables_total
FROM information_schema.tables
WHERE table_schema = DATABASE();

SELECT 'Ejecutar 02_validate_data_integrity.sql para verificar datos' AS next_step;
