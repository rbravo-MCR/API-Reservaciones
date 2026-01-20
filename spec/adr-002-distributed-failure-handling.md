# ADR 002: Manejo de Fallos Distribuidos (Resiliencia)

**Fecha**: 2026-01-19
**Estado**: Aceptado

## Contexto
El proceso de reserva involucra dos sistemas externos críticos:
1.  **Stripe** (Cobro).
2.  **Supplier** (Reserva del auto).

Existe el riesgo de que el cobro sea exitoso (Stripe OK) pero la reserva con el proveedor falle (Timeout, Caída del sistema, Rechazo).
Si esto ocurre, el cliente ya pagó pero no tiene reserva confirmada.

## Decisión
Implementar una estrategia de **Fallback a Confirmación Interna** con **Outbox Pattern**.

### Detalles de Diseño
1.  **Punto de No Retorno**:
    Una vez que Stripe confirma el pago (`payment_status = PAID`), la transacción se considera exitosa desde la perspectiva del cliente. **No se realizan reembolsos automáticos por errores técnicos posteriores.**

2.  **Estado `CONFIRMED_INTERNAL`**:
    Si el proveedor falla (después de reintentos), la reserva pasa al estado `CONFIRMED_INTERNAL`.
    Esto significa: "Tu reserva está confirmada con nosotros, estamos gestionando el código final con el proveedor".

3.  **Outbox Pattern**:
    - Las interacciones con el proveedor se manejan asíncronamente mediante una tabla `outbox_events`.
    - Si el webhook de Stripe llega, se guarda el estado `PAID` y se inserta un evento `BOOK_SUPPLIER` en la misma transacción de BD.
    - Un Worker procesa estos eventos.

4.  **Reintentos y Dead Letter Queue**:
    - El Worker reintenta la conexión con el proveedor (Backoff exponencial).
    - Si se agotan los reintentos, se marca la reserva como `CONFIRMED_INTERNAL` y se alerta a Operaciones.

## Consecuencias
### Positivas
- **Experiencia de Usuario**: El cliente nunca ve un error "técnico" después de pagar. Siempre recibe una confirmación.
- **Consistencia**: Se garantiza que si se cobró, se intentará honrar la reserva.
- **Trazabilidad**: Todo intento queda registrado en `reservation_supplier_requests`.

### Negativas
- **Carga Operativa**: Los casos `CONFIRMED_INTERNAL` requieren gestión manual (llamar al proveedor, reasignar, o reembolsar manualmente).
- **Riesgo Financiero**: Si no se puede confirmar con el proveedor y la tarifa subió, la empresa podría absorber la diferencia o tener que reembolsar (mala UX).
