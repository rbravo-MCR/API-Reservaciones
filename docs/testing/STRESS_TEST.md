# Informe de Prueba de Estrés (Load Testing)

**Fecha**: 2026-01-22
**Entorno**: Desarrollo (MySQL en AWS RDS)
**Herramienta**: Locust

---

## 📊 Resumen Ejecutivo

| Métrica | Valor |
|---------|-------|
| **Usuarios Concurrentes** | 10 |
| **Tasa de Escalamiento** | 2 usuarios/segundo |
| **Tiempo de Ejecución** | 30 segundos |
| **Total de Solicitudes** | 91 |
| **Tasa de Éxito** | **100% (0 fallos)** ✅ |
| **Tiempo de Respuesta Promedio** | 978 ms |
| **Percentil 90 (P90)** | 2500 ms |
| **RPS (Solicitudes por Segundo)** | 3.09 |

---

## 🛠️ Metodología y Configuración

### Escenario de Prueba
Se simuló la creación de reservaciones mediante el endpoint `POST /api/v1/reservations`. Cada usuario virtual cargó un payload JSON estándar y generó una clave de idempotencia única (`Idempotency-Key`) para cada solicitud.

### Infraestructura
- **API**: FastAPI ejecutándose en `localhost:8000`.
- **Base de Datos**: MySQL (AWS RDS).
- **Carga**: Ejecutada localmente en modo "headless" con Locust.

### Preparación (Seeding)
Antes de la prueba, se poblaron las tablas de referencia para asegurar la integridad de los datos y evitar errores `400 Bad Request`:
- Proveedor ID: 123
- Oficinas ID: 10, 15
- Categoría de Auto ID: 5
- Canal de Venta ID: 1
- Producto de Proveedor ID: 505

---

## 📈 Resultados Detallados

### Estadísticas por Endpoint
| Método | Endpoint | # Solicitudes | # Fallos | Promedio (ms) | Min (ms) | Max (ms) | Mediana (ms) |
|--------|----------|---------------|----------|---------------|----------|----------|--------------|
| POST | `/api/v1/reservations` | 91 | 0 | 978 | 619 | 2876 | 660 |

### Percentiles de Tiempo de Respuesta
| 50% | 66% | 75% | 80% | 90% | 95% | 98% | 99% | 100% |
|-----|-----|-----|-----|-----|-----|-----|-----|------|
| 660ms | 800ms | 940ms | 1000ms | 2500ms | 2700ms | 2900ms | 2900ms | 2900ms |

---

## 🔍 Hallazgos y Correcciones

Durante la fase de preparación de la prueba, se identificaron y resolvieron los siguientes problemas:

1.  **Bug en Esquema Pydantic**: El modelo `CreateReservationRequest` no incluía el campo `rental_days`, a pesar de tener un validador asociado. Esto impedía que el servidor iniciara correctamente. Se corrigió agregando el campo al modelo.
2.  **Integridad Referencial**: Inicialmente, la prueba falló con un 100% de errores `400 Bad Request` debido a que los IDs de referencia en el payload no existían en la base de datos. Se solucionó mediante un script de "seeding".

---

## 💡 Conclusiones

La API demuestra ser estable bajo una carga moderada de 10 usuarios concurrentes, manteniendo una tasa de éxito perfecta. Los tiempos de respuesta se encuentran dentro de rangos aceptables para una operación que involucra validaciones complejas de base de datos e integridad referencial, aunque el P90 de 2.5s sugiere que hay margen para optimizaciones en el manejo de transacciones o indexación bajo mayor carga.

---

**Preparado por**: Gemini CLI Agent
