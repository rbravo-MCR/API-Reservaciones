-- ============================================================================
-- Script 03: Simulación de Escenarios de Deadlock (PROB-007)
-- Propósito: Verificar que el retry de deadlocks funciona correctamente
-- ADVERTENCIA: Solo ejecutar en entorno de desarrollo/testing
-- Uso: Requiere dos sesiones MySQL concurrentes
-- ============================================================================

-- ============================================================================
-- INSTRUCCIONES DE USO:
-- ============================================================================
-- 1. Abrir DOS sesiones de MySQL simultáneamente:
--    Terminal 1: mysql -h <host> -u <user> -p <database>
--    Terminal 2: mysql -h <host> -u <user> -p <database>
--
-- 2. Ejecutar los comandos en el orden indicado (SESSION 1 -> SESSION 2 -> SESSION 1 -> ...)
--
-- 3. Observar que se produce un deadlock
--
-- 4. Verificar que la aplicación maneja el deadlock con retry automático
-- ============================================================================

-- ============================================================================
-- ESCENARIO 1: Deadlock Simple con 2 Reservaciones
-- ============================================================================

-- --- PREPARACIÓN (Ejecutar en cualquier sesión primero) ---
-- Crear dos reservaciones de prueba
INSERT INTO reservations (
    reservation_code, supplier_id, country_code,
    pickup_office_id, dropoff_office_id,
    car_category_id, pickup_datetime, dropoff_datetime,
    rental_days, currency_code,
    public_price_total, supplier_cost_total,
    taxes_total, fees_total, discount_total,
    commission_total, cashback_earned_amount,
    status, payment_status, sales_channel_id, lock_version
) VALUES
('DEADLOCK_TEST_001', 1, 'MX', 101, 102, 5,
 '2026-03-01 10:00:00', '2026-03-05 10:00:00', 4, 'USD',
 100.00, 80.00, 10.00, 5.00, 0.00, 5.00, 0.00,
 'PENDING', 'UNPAID', 1, 0),
('DEADLOCK_TEST_002', 1, 'MX', 101, 102, 5,
 '2026-03-01 10:00:00', '2026-03-05 10:00:00', 4, 'USD',
 100.00, 80.00, 10.00, 5.00, 0.00, 5.00, 0.00,
 'PENDING', 'UNPAID', 1, 0);

-- --- SESSION 1: Iniciar transacción y bloquear DEADLOCK_TEST_001 ---
START TRANSACTION;
UPDATE reservations
SET status = 'CONFIRMED', lock_version = lock_version + 1
WHERE reservation_code = 'DEADLOCK_TEST_001';
-- NO HACER COMMIT AÚN

-- --- SESSION 2: Iniciar transacción y bloquear DEADLOCK_TEST_002 ---
START TRANSACTION;
UPDATE reservations
SET status = 'CONFIRMED', lock_version = lock_version + 1
WHERE reservation_code = 'DEADLOCK_TEST_002';
-- NO HACER COMMIT AÚN

-- --- SESSION 1: Intentar bloquear DEADLOCK_TEST_002 (esperará) ---
UPDATE reservations
SET status = 'PAID', lock_version = lock_version + 1
WHERE reservation_code = 'DEADLOCK_TEST_002';

-- --- SESSION 2: Intentar bloquear DEADLOCK_TEST_001 (¡DEADLOCK!) ---
-- Este comando causará el deadlock - MySQL matará una de las transacciones
UPDATE reservations
SET status = 'PAID', lock_version = lock_version + 1
WHERE reservation_code = 'DEADLOCK_TEST_001';

-- Resultado esperado:
-- ERROR 1213 (40001): Deadlock found when trying to get lock; try restarting transaction

-- --- LIMPIEZA (Después del deadlock) ---
-- En la sesión que NO fue matada:
ROLLBACK;

-- Eliminar datos de prueba
DELETE FROM reservations WHERE reservation_code LIKE 'DEADLOCK_TEST_%';

-- ============================================================================
-- ESCENARIO 2: Deadlock en Outbox Events (Más realista)
-- ============================================================================

-- --- PREPARACIÓN ---
INSERT INTO outbox_events (
    event_type, aggregate_type, aggregate_code,
    payload, status, attempts, next_attempt_at, created_at
) VALUES
('BOOK_SUPPLIER', 'RESERVATION', 'OUTBOX_DEADLOCK_001',
 '{"test": true}', 'NEW', 0, NOW(), NOW()),
('BOOK_SUPPLIER', 'RESERVATION', 'OUTBOX_DEADLOCK_002',
 '{"test": true}', 'NEW', 0, NOW(), NOW());

-- --- SESSION 1: Claim primer evento ---
START TRANSACTION;
UPDATE outbox_events
SET status = 'IN_PROGRESS',
    locked_by = 'worker-1',
    locked_at = NOW(),
    lock_expires_at = DATE_ADD(NOW(), INTERVAL 30 SECOND)
WHERE aggregate_code = 'OUTBOX_DEADLOCK_001'
  AND event_type = 'BOOK_SUPPLIER'
  AND status = 'NEW';
-- NO HACER COMMIT

-- --- SESSION 2: Claim segundo evento ---
START TRANSACTION;
UPDATE outbox_events
SET status = 'IN_PROGRESS',
    locked_by = 'worker-2',
    locked_at = NOW(),
    lock_expires_at = DATE_ADD(NOW(), INTERVAL 30 SECOND)
WHERE aggregate_code = 'OUTBOX_DEADLOCK_002'
  AND event_type = 'BOOK_SUPPLIER'
  AND status = 'NEW';
-- NO HACER COMMIT

-- --- SESSION 1: Intentar actualizar segundo evento ---
UPDATE outbox_events
SET attempts = attempts + 1
WHERE aggregate_code = 'OUTBOX_DEADLOCK_002'
  AND event_type = 'BOOK_SUPPLIER';

-- --- SESSION 2: Intentar actualizar primer evento (¡DEADLOCK!) ---
UPDATE outbox_events
SET attempts = attempts + 1
WHERE aggregate_code = 'OUTBOX_DEADLOCK_001'
  AND event_type = 'BOOK_SUPPLIER';

-- --- LIMPIEZA ---
ROLLBACK; -- En ambas sesiones
DELETE FROM outbox_events WHERE aggregate_code LIKE 'OUTBOX_DEADLOCK_%';

-- ============================================================================
-- VERIFICAR CONFIGURACIÓN MYSQL PARA DEADLOCKS
-- ============================================================================
SHOW VARIABLES LIKE 'innodb_deadlock_detect';
-- Debe estar ON (default)

SHOW VARIABLES LIKE 'innodb_lock_wait_timeout';
-- Timeout en segundos antes de error 1205

SHOW ENGINE INNODB STATUS\G
-- Ver sección "LATEST DETECTED DEADLOCK" para detalles del último deadlock

-- ============================================================================
-- QUERY PARA MONITOREAR DEADLOCKS EN PRODUCCIÓN
-- ============================================================================
-- Nota: MySQL no guarda histórico de deadlocks, solo el último
-- Implementar logging en la aplicación (PROB-007 implementado con logger.warning)

SELECT
    'Para monitoreo de deadlocks en producción:' AS info,
    '1. Revisar logs de aplicación con nivel WARNING' AS step_1,
    '2. Buscar: "Database deadlock detected, retrying"' AS step_2,
    '3. Verificar métricas de reintentos en observabilidad' AS step_3;

-- ============================================================================
-- LIMPIEZA COMPLETA
-- ============================================================================
-- Ejecutar al final para limpiar todos los datos de prueba
DELETE FROM reservations WHERE reservation_code LIKE 'DEADLOCK_TEST_%';
DELETE FROM outbox_events WHERE aggregate_code LIKE 'OUTBOX_DEADLOCK_%';

SELECT 'Escenarios de deadlock completados' AS result;
SELECT 'Verificar en logs que retry_on_deadlock() manejó los errores correctamente' AS next_step;
