-- ============================================================================
-- Script 04: Limpieza de Datos de Prueba
-- Propósito: Eliminar datos de test de forma segura
-- ADVERTENCIA: SOLO EJECUTAR EN DESARROLLO/STAGING
-- Uso: mysql -h <host> -u <user> -p <database> < 04_cleanup_test_data.sql
-- ============================================================================

-- Verificar que NO estamos en producción
SELECT
    CASE
        WHEN DATABASE() LIKE '%prod%' THEN 'ERROR: Parece base de datos de producción'
        WHEN DATABASE() LIKE '%production%' THEN 'ERROR: Parece base de datos de producción'
        ELSE 'OK: Base de datos no parece producción'
    END AS safety_check,
    DATABASE() AS current_database;

-- Si el safety_check dice ERROR, DETENER AQUÍ y NO CONTINUAR

-- ============================================================================
-- ELIMINAR DATOS DE PRUEBA POR PATRÓN
-- ============================================================================

-- Eliminar reservaciones de test
DELETE FROM reservations
WHERE reservation_code LIKE 'TEST_%'
   OR reservation_code LIKE 'DEADLOCK_TEST_%'
   OR reservation_code LIKE 'INTEGRATION_TEST_%'
   OR customer_ip = '203.0.113.10'  -- IP de ejemplo RFC 5737
   OR customer_user_agent LIKE 'pytest%';

SELECT ROW_COUNT() AS reservations_deleted;

-- Eliminar contactos huérfanos
DELETE FROM reservation_contacts
WHERE reservation_code IS NULL
   OR reservation_code LIKE 'TEST_%'
   OR email LIKE '%@example.com'
   OR email LIKE '%@test.com';

SELECT ROW_COUNT() AS contacts_deleted;

-- Eliminar drivers huérfanos
DELETE FROM reservation_drivers
WHERE reservation_code IS NULL
   OR reservation_code LIKE 'TEST_%'
   OR email LIKE '%@example.com';

SELECT ROW_COUNT() AS drivers_deleted;

-- Eliminar pagos de test
DELETE FROM payments
WHERE reservation_code IS NULL
   OR reservation_code LIKE 'TEST_%'
   OR stripe_payment_intent_id LIKE 'pi_test_%';

SELECT ROW_COUNT() AS payments_deleted;

-- Eliminar idempotency keys antiguas (> 30 días)
DELETE FROM idempotency_keys
WHERE id NOT IN (
    SELECT ik.id
    FROM idempotency_keys ik
    INNER JOIN reservations r ON ik.reference_reservation_id = r.id
    WHERE r.id IS NOT NULL
)
  OR idem_key LIKE 'test_%'
  OR idem_key LIKE 'k1' OR idem_key LIKE 'k2' OR idem_key LIKE 'k3'; -- Tests unitarios

SELECT ROW_COUNT() AS idempotency_keys_deleted;

-- Eliminar eventos de outbox completados (> 7 días)
DELETE FROM outbox_events
WHERE status = 'DONE'
  AND created_at < DATE_SUB(NOW(), INTERVAL 7 DAY);

SELECT ROW_COUNT() AS outbox_events_cleaned;

-- Eliminar eventos de outbox fallidos muy antiguos (> 30 días)
DELETE FROM outbox_events
WHERE status = 'FAILED'
  AND created_at < DATE_SUB(NOW(), INTERVAL 30 DAY);

SELECT ROW_COUNT() AS old_failed_events_deleted;

-- Eliminar supplier requests antiguas (> 30 días)
DELETE FROM reservation_supplier_requests
WHERE id NOT IN (
    SELECT rsr.id
    FROM reservation_supplier_requests rsr
    INNER JOIN reservations r ON rsr.reservation_code = r.reservation_code
    WHERE r.id IS NOT NULL
      AND r.status != 'CANCELLED'
);

SELECT ROW_COUNT() AS orphan_supplier_requests_deleted;

-- ============================================================================
-- LIMPIAR DEAD LETTER QUEUE (con precaución)
-- ============================================================================
-- Solo eliminar eventos DLQ resueltos manualmente (requiere columna 'resolved')
-- Comentado por seguridad - descomentar solo si es necesario
/*
DELETE FROM outbox_dead_letters
WHERE resolved_at IS NOT NULL
  AND resolved_at < DATE_SUB(NOW(), INTERVAL 30 DAY);

SELECT ROW_COUNT() AS resolved_dlq_deleted;
*/

SELECT 'DLQ: No se eliminaron eventos - revisar manualmente' AS dlq_info;

-- ============================================================================
-- RESUMEN DE LIMPIEZA
-- ============================================================================
SELECT '============ RESUMEN DE LIMPIEZA ============' AS summary;

SELECT
    (SELECT COUNT(*) FROM reservations) AS remaining_reservations,
    (SELECT COUNT(*) FROM payments) AS remaining_payments,
    (SELECT COUNT(*) FROM outbox_events) AS remaining_outbox,
    (SELECT COUNT(*) FROM outbox_dead_letters) AS remaining_dlq,
    (SELECT COUNT(*) FROM idempotency_keys) AS remaining_idempotency_keys;

SELECT 'Limpieza completada' AS result;
