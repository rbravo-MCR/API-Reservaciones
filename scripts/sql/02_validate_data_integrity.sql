-- ============================================================================
-- Script 02: Validación de Integridad de Datos
-- Propósito: Verificar constraints, datos maestros y consistencia
-- Uso: mysql -h <host> -u <user> -p <database> < 02_validate_data_integrity.sql
-- ============================================================================

-- ============================================================================
-- 1. VERIFICAR DATOS MAESTROS REQUERIDOS
-- ============================================================================
SELECT 'DATOS MAESTROS: suppliers' AS check_name,
    CASE
        WHEN COUNT(*) >= 1 THEN CONCAT('✓ ', COUNT(*), ' suppliers configurados')
        ELSE '✗ No hay suppliers - CRÍTICO'
    END AS status,
    GROUP_CONCAT(DISTINCT code ORDER BY code) AS supplier_codes
FROM suppliers
WHERE is_active = 1;

SELECT 'DATOS MAESTROS: offices' AS check_name,
    CASE
        WHEN COUNT(*) >= 2 THEN CONCAT('✓ ', COUNT(*), ' offices configuradas')
        ELSE '✗ Mínimo 2 offices requeridas (pickup/dropoff)'
    END AS status
FROM offices;

SELECT 'DATOS MAESTROS: car_categories' AS check_name,
    CASE
        WHEN COUNT(*) >= 1 THEN CONCAT('✓ ', COUNT(*), ' categorías disponibles')
        ELSE '✗ No hay categorías - CRÍTICO'
    END AS status
FROM car_categories;

SELECT 'DATOS MAESTROS: sales_channels' AS check_name,
    CASE
        WHEN COUNT(*) >= 1 THEN CONCAT('✓ ', COUNT(*), ' canales configurados')
        ELSE '✗ No hay canales de venta'
    END AS status
FROM sales_channels;

-- ============================================================================
-- 2. VERIFICAR CONSISTENCIA DE RESERVACIONES
-- ============================================================================
SELECT 'INTEGRIDAD: Reservaciones sin código' AS check_name,
    CASE
        WHEN COUNT(*) = 0 THEN '✓ Todas las reservaciones tienen código'
        ELSE CONCAT('✗ ', COUNT(*), ' reservaciones sin código único')
    END AS status
FROM reservations
WHERE reservation_code IS NULL OR reservation_code = '';

SELECT 'INTEGRIDAD: Reservaciones con lock_version NULL' AS check_name,
    CASE
        WHEN COUNT(*) = 0 THEN '✓ Optimistic locking configurado'
        ELSE CONCAT('✗ ', COUNT(*), ' reservaciones sin lock_version - PROB-001')
    END AS status
FROM reservations
WHERE lock_version IS NULL;

SELECT 'INTEGRIDAD: Duplicados en reservation_code' AS check_name,
    CASE
        WHEN COUNT(*) = 0 THEN '✓ No hay códigos duplicados'
        ELSE CONCAT('✗ ', COUNT(*), ' códigos duplicados - CRÍTICO')
    END AS status
FROM (
    SELECT reservation_code, COUNT(*) as cnt
    FROM reservations
    GROUP BY reservation_code
    HAVING cnt > 1
) AS duplicates;

-- ============================================================================
-- 3. VERIFICAR PAGOS
-- ============================================================================
SELECT 'INTEGRIDAD: Pagos sin reservación' AS check_name,
    CASE
        WHEN COUNT(*) = 0 THEN '✓ Todos los pagos tienen reservación válida'
        ELSE CONCAT('✗ ', COUNT(*), ' pagos huérfanos')
    END AS status
FROM payments p
LEFT JOIN reservations r ON p.reservation_id = r.id
WHERE r.id IS NULL;

SELECT 'INTEGRIDAD: Reservaciones PAID sin pago registrado' AS check_name,
    CASE
        WHEN COUNT(*) = 0 THEN '✓ Consistencia payment_status OK'
        ELSE CONCAT('⚠ ', COUNT(*), ' reservaciones PAID sin payment record')
    END AS status
FROM reservations r
LEFT JOIN payments p ON r.id = p.reservation_id
WHERE r.payment_status = 'PAID' AND p.id IS NULL;

-- ============================================================================
-- 4. VERIFICAR IDEMPOTENCY KEYS
-- ============================================================================
SELECT 'IDEMPOTENCIA: Keys duplicadas en mismo scope' AS check_name,
    CASE
        WHEN COUNT(*) = 0 THEN '✓ No hay duplicados (PROB-001 OK)'
        ELSE CONCAT('✗ ', COUNT(*), ' duplicados - PROB-001 FALLANDO')
    END AS status
FROM (
    SELECT scope, idem_key, COUNT(*) as cnt
    FROM idempotency_keys
    GROUP BY scope, idem_key
    HAVING cnt > 1
) AS duplicates;

SELECT 'IDEMPOTENCIA: Total de keys registradas' AS check_name,
    CONCAT('ℹ ', COUNT(*), ' keys en total') AS status,
    COUNT(DISTINCT scope) AS scopes_used
FROM idempotency_keys;

-- ============================================================================
-- 5. VERIFICAR OUTBOX EVENTS
-- ============================================================================
SELECT 'OUTBOX: Eventos en estado NEW o RETRY' AS check_name,
    CASE
        WHEN COUNT(*) = 0 THEN '✓ No hay eventos pendientes'
        ELSE CONCAT('ℹ ', COUNT(*), ' eventos esperando procesamiento')
    END AS status,
    COUNT(CASE WHEN status = 'NEW' THEN 1 END) AS new_count,
    COUNT(CASE WHEN status = 'RETRY' THEN 1 END) AS retry_count
FROM outbox_events
WHERE status IN ('NEW', 'RETRY');

SELECT 'OUTBOX: Eventos con lock expirado' AS check_name,
    CASE
        WHEN COUNT(*) = 0 THEN '✓ No hay locks expirados'
        ELSE CONCAT('⚠ ', COUNT(*), ' eventos con lock expirado (retry automático)')
    END AS status
FROM outbox_events
WHERE lock_expires_at IS NOT NULL
  AND lock_expires_at < NOW()
  AND status = 'IN_PROGRESS';

SELECT 'OUTBOX: Distribución por estado' AS check_name,
    status,
    COUNT(*) AS count,
    AVG(attempts) AS avg_attempts
FROM outbox_events
GROUP BY status
ORDER BY count DESC;

-- ============================================================================
-- 6. VERIFICAR DEAD LETTER QUEUE (PROB-003)
-- ============================================================================
SELECT 'DLQ: Eventos en Dead Letter Queue' AS check_name,
    CASE
        WHEN COUNT(*) = 0 THEN '✓ No hay eventos fallidos permanentemente'
        ELSE CONCAT('⚠ ', COUNT(*), ' eventos requieren intervención manual')
    END AS status,
    AVG(attempts) AS avg_attempts_before_dlq
FROM outbox_dead_letters;

SELECT 'DLQ: Eventos por tipo de error' AS check_name,
    error_code,
    COUNT(*) AS count,
    MAX(moved_at) AS last_moved
FROM outbox_dead_letters
GROUP BY error_code
ORDER BY count DESC
LIMIT 10;

-- ============================================================================
-- 7. VERIFICAR SUPPLIER REQUESTS
-- ============================================================================
SELECT 'SUPPLIER_REQUESTS: Tasa de éxito' AS check_name,
    CONCAT(
        ROUND(SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2),
        '% success rate'
    ) AS status,
    SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) AS success_count,
    SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) AS failed_count
FROM reservation_supplier_requests;

SELECT 'SUPPLIER_REQUESTS: Errores más comunes' AS check_name,
    error_code,
    COUNT(*) AS count
FROM reservation_supplier_requests
WHERE status = 'FAILED' AND error_code IS NOT NULL
GROUP BY error_code
ORDER BY count DESC
LIMIT 5;

-- ============================================================================
-- 8. RESUMEN GENERAL
-- ============================================================================
SELECT '============ RESUMEN DE INTEGRIDAD ============' AS summary;

SELECT
    (SELECT COUNT(*) FROM reservations) AS total_reservations,
    (SELECT COUNT(*) FROM payments) AS total_payments,
    (SELECT COUNT(*) FROM outbox_events WHERE status IN ('NEW', 'RETRY')) AS pending_events,
    (SELECT COUNT(*) FROM outbox_dead_letters) AS dlq_events,
    (SELECT COUNT(*) FROM idempotency_keys) AS idempotency_keys;

SELECT 'Ejecutar 03_test_deadlock_scenario.sql para pruebas de concurrencia' AS next_step;
