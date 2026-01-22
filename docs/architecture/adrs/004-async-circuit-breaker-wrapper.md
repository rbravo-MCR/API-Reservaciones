# ADR 004: Implementación de Wrapper Asíncrono para Circuit Breaker (PyBreaker)

## Estado
Aceptado

## Contexto
El proyecto utiliza la librería `pybreaker` para implementar el patrón de Circuit Breaker en las llamadas a proveedores externos (Stripe, Suppliers). Sin embargo, se identificaron dos problemas críticos:
1.  **Incompatibilidad con Async/Await**: El método `call_async` de `pybreaker` (v1.x) tiene un bug interno que intenta utilizar `gen.coroutine` de Tornado sin haberlo importado, lanzando un `NameError`.
2.  **Interfaz de Listeners**: La versión de la librería espera que los listeners implementen métodos específicos (`before_call`, `success`, `failure`) que no estaban presentes en la implementación inicial.

## Decisión
Se ha decidido implementar un wrapper manual asíncrono en `app/infrastructure/circuit_breaker.py` llamado `async_supplier_breaker`.

### Detalles Técnicos:
- El wrapper utiliza `supplier_breaker.call(func, *args, **kwargs)` pero envolviendo la ejecución en un contexto asíncrono.
- Se corrigió el `CircuitBreakerListener` para heredar de la clase base de `pybreaker` (si existe) o implementar todos los métodos requeridos para evitar `AttributeError`.
- El decorador permite que las funciones `async` sigan siendo asíncronas mientras el estado del breaker (OPEN, CLOSED, HALF_OPEN) es gestionado correctamente.

### Ejemplo de Uso:
```python
@async_supplier_breaker
async def book(self, ...):
    # Lógica asíncrona
    pass
```

## Consecuencias
- **Positivas**:
    - Tolerancia a fallos funcional para todas las llamadas asíncronas a proveedores.
    - Eliminación de errores de tiempo de ejecución (`NameError`, `AttributeError`).
    - Mantenemos la lógica de negocio limpia de chequeos de estado manuales.
- **Negativas**:
    - Dependencia de un wrapper manual que debe ser mantenido si se actualiza la librería `pybreaker` a una versión con soporte nativo robusto para `asyncio`.
