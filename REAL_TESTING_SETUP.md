# Guía de Pruebas "Crudo y Rudo" (Real World Testing)

Esta guía documenta cómo ejecutar la aplicación y las pruebas en un entorno **REAL**, sin mocks ni bases de datos en memoria. El objetivo es probar la integración completa con una base de datos MySQL y servicios externos.

## 1. Requisitos Previos

- **Docker & Docker Compose**: Para levantar la base de datos localmente.
- **Python 3.10+ & `uv`**: Para ejecutar la aplicación.
- **Claves de Stripe (Test Mode)**: Necesarias para procesar pagos reales en modo test.

## 2. Configuración de Infraestructura (Base de Datos)

Como el repositorio no incluye un `docker-compose.yml` por defecto, crea uno en la raíz del proyecto con el siguiente contenido para levantar una instancia de MySQL compatible:

```yaml
version: '3.8'

services:
  db:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: root
      MYSQL_DATABASE: cro_database
      MYSQL_USER: user
      MYSQL_PASSWORD: password
    ports:
      - "3306:3306"
    command: --default-authentication-plugin=mysql_native_password
    volumes:
      - db_data:/var/lib/mysql

volumes:
  db_data:
```

Levanta la base de datos:

```bash
docker-compose up -d
```

## 3. Configuración de Variables de Entorno (.env)

Crea un archivo `.env` (si no existe) basado en `.env.example` y configúralo para **DESACTIVAR** el modo en memoria y apuntar a tu BD local:

```ini
# .env

# CRÍTICO: Desactivar modo memoria
USE_IN_MEMORY=false

# Conexión a la BD Docker (ajusta host/puerto si es necesario)
# Formato: mysql+aiomysql://USER:PASSWORD@HOST:PORT/DB_NAME
DATABASE_URL=mysql+aiomysql://user:password@localhost:3306/cro_database

# Stripe (Keys de prueba reales)
STRIPE_API_KEY=sk_test_... (Tu Secret Key de Stripe)
STRIPE_WEBHOOK_SECRET=whsec_... (Tu Webhook Secret, opcional si no pruebas webhooks)

# Configuración de Proveedores (Simulados o Reales)
# Si tienes endpoints reales de proveedores, configúralos aquí.
SUPPLIER_BASE_URL=http://localhost:8000/mock_supplier
```

## 4. Inicialización de la Base de Datos

Una vez que MySQL esté corriendo y el `.env` configurado, inicializa el esquema y los datos semilla.

1.  **Limpiar BD (Opcional):**
    ```bash
    uv run python scripts/drop_all.py
    ```

2.  **Verificar conexión:**
    ```bash
    uv run python scripts/check_db.py
    ```

3.  **Sembrar datos (Seed):**
    Este script crea las tablas y datos básicos (proveedores, oficinas, autos).
    ```bash
    uv run python scripts/seed_db.py
    ```

## 5. Ejecutar la Aplicación "En Crudo"

Levanta el servidor apuntando a la infraestructura real.

```bash
uv run uvicorn app.main:app --reload
```

El servidor estará disponible en `http://localhost:8000`.

## 6. Pruebas Manuales "Rudas" (cURL)

Prueba el flujo completo: Crear Reserva -> Pagar -> Obtener Recibo.

### A. Crear una Reserva
```bash
curl -X POST "http://localhost:8000/api/v1/reservations" \
     -H "Content-Type: application/json" \
     -H "Idempotency-Key: real-test-001" \
     -d '{
           "supplier_id": 1,
           "pickup_office_id": 1,
           "dropoff_office_id": 1,
           "car_category_id": 1,
           "pickup_datetime": "2026-02-01T10:00:00",
           "dropoff_datetime": "2026-02-05T10:00:00",
           "rental_days": 4,
           "currency_code": "USD",
           "public_price_total": "100.00",
           "supplier_cost_total": "80.00",
           "taxes_total": "10.00",
           "fees_total": "5.00",
           "discount_total": "0.00",
           "commission_total": "5.00",
           "contacts": [{"contact_type": "BOOKER", "full_name": "Real Tester", "email": "test@real.com"}],
           "drivers": [{"is_primary_driver": true, "first_name": "Real", "last_name": "Driver"}]
         }'
```
**Respuesta esperada:** JSON con `reservation_code` (ej. `RES-XXXXXXXX`).

### B. Pagar Reserva (Simulación Real con Stripe)
Usa el `reservation_code` obtenido en el paso anterior.

```bash
curl -X POST "http://localhost:8000/api/v1/reservations/RES-XXXXXXXX/pay" \
     -H "Content-Type: application/json" \
     -H "Idempotency-Key: pay-test-001" \
     -d '{
           "payment_token": "tok_visa",
           "amount": 10000,
           "currency": "usd"
         }'
```
*Nota: `tok_visa` es un token de prueba válido de Stripe.*

### C. Verificar Recibo
```bash
curl -X GET "http://localhost:8000/api/v1/reservations/RES-XXXXXXXX/receipt"
```

## 7. Ejecutar Tests Automatizados contra BD Real

Pytest está configurado para detectar variables de entorno y cambiar el comportamiento.

Para correr los tests de integración usando la base de datos MySQL real (definida en `.env` o `TEST_DATABASE_URL`):

```bash
# Windows (PowerShell)
$env:TEST_USE_REAL_DB="true"; uv run pytest tests/integration -v

# Linux/Mac
TEST_USE_REAL_DB=true uv run pytest tests/integration -v
```

**¡Advertencia!**: Esto borrará/modificará datos en la base de datos configurada en `TEST_DATABASE_URL`. Asegúrate de usar una base de datos de pruebas dedicada, NO la de producción.

