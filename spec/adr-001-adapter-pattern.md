# ADR 001: Patrón Adapter para Proveedores Globales

**Fecha**: 2026-01-19
**Estado**: Aceptado

## Contexto
El sistema debe integrarse con múltiples proveedores globales de alquiler de autos (Hertz, Budget, Europcar, etc.).
Cada proveedor tiene:
- Protocolos diferentes (SOAP/XML, REST/JSON).
- Estructuras de datos distintas.
- Códigos de error y estados variados.

## Decisión
Implementar el **Patrón Adapter** para normalizar la comunicación con todos los proveedores.

### Detalles de Diseño
1.  **Interfaz Común (`SupplierGateway`)**:
    Definir una interfaz única en la capa de Aplicación que todos los adaptadores deben implementar.
    ```python
    class SupplierGateway(ABC):
        async def book_reservation(self, reservation: ReservationSnapshot) -> SupplierBookingResponse: ...
        async def cancel_reservation(self, supplier_code: str) -> bool: ...
    ```

2.  **Adaptadores Específicos**:
    Crear implementaciones concretas en la capa de Infraestructura (`HertzAdapter`, `BudgetAdapter`).
    Cada adaptador es responsable de:
    - Transformar el modelo de dominio (`ReservationSnapshot`) al formato del proveedor (XML/JSON).
    - Manejar la autenticación específica del proveedor.
    - Mapear los errores del proveedor a excepciones de dominio estándar (`SupplierTimeoutError`, `SupplierRefusalError`).

3.  **Factory/Registry**:
    Usar un mecanismo para instanciar el adaptador correcto basado en el `supplier_id` de la reserva.

## Consecuencias
### Positivas
- **Desacoplamiento**: El núcleo del negocio no conoce los detalles de implementación de cada proveedor.
- **Extensibilidad**: Agregar un nuevo proveedor solo requiere crear una nueva clase Adapter sin tocar la lógica de negocio.
- **Testabilidad**: Se puede usar un `MockSupplierAdapter` para pruebas sin depender de servicios externos.

### Negativas
- **Complejidad Inicial**: Requiere definir una interfaz genérica robusta que cubra todos los casos de uso posibles.
- **Mantenimiento**: Si un proveedor cambia drásticamente su API, el adaptador debe actualizarse.
