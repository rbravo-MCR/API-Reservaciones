# Matriz de Trazabilidad: Migración Legacy (PHP → Python)

Este documento registra la paridad funcional entre el sistema legado en PHP y la nueva implementación en Python/FastAPI para los Gateways de proveedores.

## Resumen de Proveedores Migrados

| Proveedor | Archivo PHP Legacy | Gateway Python (Infraestructura) | Tests de Paridad | Notas de Implementación |
| :--- | :--- | :--- | :--- | :--- |
| **Hertz Argentina** | `HertzArgentinaRepository.php` | `HertzArgentinaGateway` | `test_hertz_argentina_gateway.py` | Implementa Auth interna por Token (OAuth2). |
| **Infinity Group** | `InfinityGroupRepository.php` | `InfinityGroupGateway` | `test_infinity_group_gateway.py` | Comunicación XML vía GET (OTA standard). |
| **Localiza** | `LocalizaRepository.php` | `LocalizaGateway` | `test_localiza_gateway.py` | Lógica de reserva inferida de OTA standard (PHP solo tenía Avail). |
| **Mex Group** | `MexGroupRepository.php` | `MexGroupGateway` | `test_mex_group_gateway.py` | REST JSON con Auth por Token cacheable. |
| **National Group** | `NationalGroupRepository.php` | `NationalGroupGateway` | `test_national_group_gateway.py` | REST JSON con Token estático. |
| **Niza Cars** | `NizaCarsRepository.php` | `NizaCarsGateway` | `test_niza_cars_gateway.py` | SOAP 1.1 (Rentway). Mapeo de grupos y planes. |
| **Noleggiare** | `NoleggiareRepository.php` | `NoleggiareGateway` | `test_noleggiare_gateway.py` | SOAP 1.1 (OTA standard). POS Auth. |

## Mapeo de Funciones Críticas

### 1. Hertz Argentina
- **PHP**: `getToken()`, `createBooking($params)`
- **Python**: `_get_token()`, `book(reservation_code, idem_key, snapshot)`
- **Paridad**: 100% en payload JSON. Cálculo de edad migrado.

### 2. Infinity Group
- **PHP**: `generateVehResXml($reservation, $quotation)`, `sendOtaXmlRequest($xml)`
- **Python**: `book(...)` con f-string XML template.
- **Paridad**: Idéntica estructura XML (OTA_VehResRQ).

### 3. Localiza
- **PHP**: `buildVehAvailRateRequest($params)` (Solo disponibilidad)
- **Python**: `book(...)` implementando `OTA_VehResRQ` (Estándar OTA).
- **Paridad**: Mejora funcional (se añade capacidad de reserva).

### 4. Mex Group
- **PHP**: `confirmSingleReservation($reservation)`, `login()`
- **Python**: `book(...)`, `_get_token()`
- **Paridad**: 100% REST JSON. Se simplifica la lógica de "recotización" delegándola al snapshot.

### 5. National Group
- **PHP**: `setNationalGroupBookings()`
- **Python**: `book(...)`
- **Paridad**: 100% REST JSON. Formato de fecha ISO-8601 preservado.

### 6. Niza Cars
- **PHP**: `createReservation($params)`, `call($key, $payload)`
- **Python**: `book(...)` implementando SOAP 1.1 manual.
- **Paridad**: 100% SOAP structure. Mapeo de `Surname,GivenName` para el Driver.

### 7. Noleggiare
- **PHP**: `reserve($data)`, `posBlock()`, `wrapEnvelope($innerXml)`
- **Python**: `book(...)` con generación de `EchoToken` y `TimeStamp` dinámico.
- **Paridad**: 100% OTA/SOAP standard.

## Reglas de Oro Aplicadas
- **Tolerancia a Fallos**: Todos los gateways usan el decorador `@async_supplier_breaker`.
- **Inmutabilidad**: Los gateways no modifican el estado de la reserva directamente; retornan un `SupplierBookingResult`.
- **Defensivo**: Validación estricta de presencia de datos en el `reservation_snapshot`.
