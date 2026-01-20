# Informe de Análisis: Orquestador de Backend de Reservas

**Para:** Project Manager / Lead Architect
**De:** Analista Sr. de Sistemas (Enfoque: Optimización y Ciclo de Vida)
**Fecha:** 16 de Enero, 2026
**Asunto:** Revisión del documento `Orquestador.md` y alineación con infraestructura de datos.

---

## 1. Resumen Ejecutivo
El documento `Orquestador.md` establece un marco de trabajo sólido basado en **Vertical Slices** y desarrollo iterativo guiado por agentes. La arquitectura propuesta (Outbox Pattern, Optimistic Locking) es adecuada para un sistema transaccional distribuido de alta concurrencia. Sin embargo, existen ambigüedades críticas en la definición del alcance ("NO auth", "NO disponibilidad") y en la gestión de errores distribuidos que podrían impactar la integridad de los datos y la experiencia del usuario final.

---

## 2. Análisis del Ciclo de Vida y Arquitectura

### Puntos Fuertes Detectados:
*   **Patrones de Resiliencia:** El uso de `outbox_events` y `idempotency_keys` es excelente para garantizar consistencia eventual y evitar duplicidad en transacciones financieras (Stripe) y con proveedores.
*   **Control de Concurrencia:** La implementación de `lock_version` en la tabla `reservations` mitiga eficazmente las condiciones de carrera (race conditions).
*   **Trazabilidad:** La tabla `reservation_supplier_requests` permite una auditoría clara de la comunicación con terceros, vital para depuración en producción.

### Puntos Débiles / Riesgos:
*   **Mezcla de Metodologías:** Se propone un desarrollo por "Vertical Slices" (ágil/iterativo), pero las Fases A-G describen un flujo en cascada (Waterfall) dentro de cada slice. Esto puede generar cuellos de botella si la Fase A (Análisis) no considera implicaciones de la Fase E (QA/Stress) desde el inicio.
*   **Gestión de Estados Incompleta:** No se define cómo manejar el estado "limbo" donde el pago es exitoso (Stripe) pero el proveedor falla o rechaza la reserva.

---

## 3. Detección de Ambigüedades (Fallas Potenciales)

1.  **"NO auth" (Línea 15):**
    *   *Riesgo:* ¿Significa que la API es pública y cualquiera puede crear reservas? ¿O que la autenticación se delega a un Gateway/Kong?
    *   *Impacto:* Si no hay trazabilidad del usuario (`customer_id` no existe en tablas, solo `sales_channel_id`), se pierde capacidad de CRM y seguridad básica.

2.  **"NO disponibilidad" (Línea 15):**
    *   *Riesgo:* Un sistema de reservas sin chequeo de disponibilidad es propenso a *overbooking*.
    *   *Ambigüedad:* ¿Se asume que el inventario es infinito o que la validación de disponibilidad es responsabilidad exclusiva del Supplier en tiempo real (síncrono)?

3.  **Integración con Suppliers (Línea 11):**
    *   *Ambigüedad:* "SOAP/XML o REST". No se define una capa de abstracción (Adapter/Facade). Si cada supplier tiene una implementación ad-hoc en el núcleo, el mantenimiento será costoso.

4.  **Regla del Recibo (Línea 23):**
    *   *Falla Lógica:* "El recibo se devuelve solo cuando la reserva esté CONFIRMED".
    *   *Escenario de Error:* El usuario paga, pero el supplier tarda 30 segundos en confirmar. ¿La API hace *timeout*? ¿Se devuelve un 202 Accepted? El contrato de la API debe reflejar asincronía si la confirmación no es inmediata.

---

## 4. Sugerencias de Mejora (Optimización)

### A. Refinamiento del Flujo de Estados (State Machine)
Definir explícitamente los estados en la tabla `reservations` para manejar la asincronía:
*   `DRAFT` -> `PENDING_PAYMENT` -> `PAID` -> `PENDING_SUPPLIER` -> `CONFIRMED` (o `SUPPLIER_REJECTED`).
*   *Acción:* Crear un diagrama de estados en la Fase B que cubra los escenarios de fallo (compensación/reembolso automático).

### B. Estrategia de Testing "Shift-Left"
Mover la definición de pruebas de carga (Fase E) a la Fase B (Arquitectura).
*   *Por qué:* El `Optimistic Locking` y el `Outbox Pattern` deben probarse bajo estrés desde el diseño, no al final.

### C. Normalización de Datos de Auditoría
La tabla `reservation_supplier_requests` usa `JSON` para payloads.
*   *Mejora:* Asegurar que existan índices en columnas clave extraídas o columnas virtuales generadas (MySQL 5.7+) para buscar logs por `booking_reference` del proveedor sin hacer full-scan del JSON.

### D. Clarificación de "NO Auth"
Si es una API B2B (para afiliados), agregar validación de `API Key` o `Client ID` asociada al `sales_channel_id` o `affiliate_id` presente en la tabla `reservations`, aunque no haya gestión de usuarios finales.

---

## 5. Conclusión para el Project Manager

El documento es un buen punto de partida para un MVP técnico ("Vertical Slice"), pero **requiere cerrar las definiciones de negocio sobre el manejo de errores en tiempo real** antes de orquestar a los agentes de desarrollo. La falta de definición en la recuperación ante fallos del proveedor (post-pago) es el riesgo más alto para la operación.

**Siguiente paso recomendado:** Ejecutar la **Fase A** enfocándose exclusivamente en definir el contrato de la API para escenarios de error (4xx, 5xx, timeouts) y el diagrama de secuencia para la transacción distribuida.
