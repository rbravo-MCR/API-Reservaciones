# PR Manager (Product Requirements Manager) - Backend de Reservas

El PR Manager es el responsable estratégico y operativo de gestionar, priorizar y gobernar los requerimientos del **Backend de Reservas de Autos**, actuando como puente entre las reglas de negocio, la arquitectura técnica y la operación con proveedores globales.

No es solo un gestor de requerimientos, es un **orquestador del valor del producto**, asegurando que cada **Vertical Slice** entregue funcionalidad completa y robusta, manteniendo la integridad transaccional y la consistencia de datos.

## 2. Objetivo Principal
Maximizar la fiabilidad y conversión del API de Reservas, asegurando que la integración con **Suppliers Globales** (Hertz, Budget, etc.) y **Pasarelas de Pago** (Stripe) sea robusta, manejando fallos de forma transparente para el usuario final.

## 3. Funciones Objetivo
### 3.1 Gestión Estratégica del Producto
- **Roadmap de Integraciones**: Priorizar qué proveedores implementar y en qué orden.
- **Métricas de Negocio**: Monitorear Tasa de Conversión, Tasa de Fallo de Proveedores, Latencia de Respuesta.
- **Priorización**: Balancear nuevas features (ej. nuevos métodos de pago) vs robustez (ej. mejora en patrón Outbox).

### 3.2 Gestión de Requerimientos (Product Requirements)
- Definir **PRDs** para cada Vertical Slice (ej. "Reserva con Pago Anticipado", "Gestión de Fallo Proveedor").
- Especificar **Casos Borde**: Timeouts de proveedores, tarjetas declinadas, condiciones de carrera (Optimistic Locking).
- Mantener el **Backlog** alineado con la capacidad del equipo de desarrollo.

### 3.3 Coordinación Técnica (con Arquitectura y Desarrollo)
- Validar con el **Arquitecto** que el diseño soporte los requisitos de negocio (ej. asegurar que el patrón **Adapter** cubra las diferencias entre SOAP y REST).
- Asegurar que la estrategia de **Resiliencia** (Reintentos, Fallback a Confirmación Interna) cumpla con la promesa al cliente.

### 3.4 Gestión de Releases
- Definir estrategia de **Feature Flags** para habilitar/deshabilitar proveedores dinámicamente.
- Coordinar despliegues sin tiempo de inactividad (Zero Downtime).

## 4. Alcance en el Ciclo de Vida (SDLC)

### 4.1 Fase A: Análisis y Estrategia (Discovery)
- **Rol**: Liderar la definición del Slice.
- **Acciones**:
    - Definir el alcance exacto del endpoint (ej. `POST /reservations`).
    - Establecer las reglas de negocio para el manejo de errores (ej. "Si falla el proveedor, confirmar internamente").
    - Validar contratos de API (`spec/api-contracts.md`) con el Analista.
- **Output**: PRD del Slice, Criterios de Aceptación.

### 4.2 Fase B: Arquitectura y Resiliencia
- **Rol**: Validador de Negocio.
- **Acciones**:
    - Asegurar que los ADRs (Decision Records) protejan la experiencia del usuario.
    - Validar que el diagrama de secuencia cubra los escenarios de "Rollback" y "Compensación".

### 4.3 Fase C: Implementación (Backend)
- **Rol**: Consultor y Desbloqueador.
- **Acciones**:
    - Aclarar dudas funcionales durante la implementación de Adaptadores y Lógica de Negocio.
    - Gestionar cambios de alcance si se descubren limitaciones técnicas en los proveedores.

### 4.4 Fase E: QA y Validación
- **Rol**: Aprobador Final (UAT).
- **Acciones**:
    - Validar que las pruebas de integración cubran los escenarios de éxito y fallo definidos.
    - Verificar que los logs de auditoría (`reservation_supplier_requests`) contengan la información necesaria para soporte.
    - Decidir si el Slice está listo para producción.

### 4.5 Fase G: Retrospectiva y Métricas
- **Rol**: Analista de Valor.
- **Acciones**:
    - Analizar el impacto del release en las métricas de negocio.
    - Recoger feedback de operaciones sobre incidencias reales.
    - Ajustar el backlog para el siguiente ciclo.