# Análisis de Manejo de Tiempo (AWS EC2 + DB)

**Contexto**: Backend en AWS EC2, Base de Datos MySQL, Reservas Globales (Múltiples Timezones).

## 1. El Problema de la Relatividad Temporal
Una reserva en Argentina (`-03:00`) creada por un servidor en Virginia (`-05:00`) y guardada en una BD en Ohio (`-05:00`) puede generar errores de cálculo de días de renta si no se estandariza.

## 2. Estrategia "UTC Everywhere" (Recomendada)

### A. Infraestructura (AWS EC2)
*   **Configuración del OS**: Las instancias EC2 deben estar configuradas en **UTC** (`Etc/UTC`).
    *   *Comando*: `sudo timedatectl set-timezone Etc/UTC`
    *   *Por qué*: Evita problemas con el cambio de horario de verano (DST) del servidor mismo. Los logs del sistema y cronjobs correrán en UTC.

### B. Base de Datos (MySQL)
*   **Configuración**: El servidor MySQL debe tener `default-time-zone = '+00:00'`.
*   **Tipo de Dato**: Usar `DATETIME` o `TIMESTAMP`.
    *   *Recomendación*: Guardar siempre en **UTC**.
    *   *Ejemplo*: Si el cliente envía `10:00 AM Argentina (-03:00)`, se guarda `13:00 PM UTC`.

### C. Aplicación (Python/FastAPI)
*   **Input**: Recibe ISO 8601 con Offset (`2026-02-15T10:00:00-03:00`).
*   **Procesamiento**:
    1.  Parsear fecha con `datetime.fromisoformat()`.
    2.  Convertir inmediatamente a UTC: `.astimezone(timezone.utc)`.
    3.  **Calcular Días de Renta**: Usar la fecha localizada (Argentina) para calcular días, NO la UTC, para respetar la percepción del usuario (ej. devolver el auto a la misma hora local).
*   **Output**: Devolver ISO 8601 en UTC (`Z`) o convertir al timezone de la oficina si el frontend lo requiere explícitamente.

## 3. Matriz de Conversión

| Capa | Configuración | Valor Ejemplo (Input: 10:00 ARG) |
| :--- | :--- | :--- |
| **Cliente (Frontend)** | Local (Browser) | `2026-02-15T10:00:00-03:00` |
| **EC2 (Backend)** | UTC | Recibe Offset, convierte a `2026-02-15T13:00:00Z` |
| **MySQL (DB)** | UTC | Guarda `2026-02-15 13:00:00` |
| **Recibo (PDF/Email)** | **Timezone Oficina** | Convierte UTC -> `America/Argentina/Buenos_Aires` -> `10:00 AM` |

## 4. Riesgos y Mitigación

*   **Riesgo**: Calcular "Días de Renta" usando UTC cuando el pickup y dropoff están en zonas diferentes (Cross-border).
    *   *Solución*: Calcular la duración basándose en la hora local de la oficina de *Pickup* para el inicio y *Dropoff* para el fin, normalizando diferencias si es necesario.
*   **Riesgo**: "Daylight Saving Time" (Cambio de hora).
    *   *Solución*: Al usar librerías como `zoneinfo` (Python 3.9+) y guardar el ID de zona (`America/Mexico_City`), el sistema ajusta automáticamente si una fecha cae en horario de verano o invierno.

## 5. Conclusión para el Desarrollador
1.  No confiar en `datetime.now()`. Usar siempre `datetime.now(timezone.utc)`.
2.  Asegurar que la conexión SQLAlchemy tenga `init_command='SET time_zone = "+00:00"'`.
3.  Persistir el `timezone` de la oficina en la tabla `offices` para poder reconstruir la hora local.

## 6. Caso de Estudio: Renta en España vs Servidor en AWS (Oregon/México)

**Escenario**:
*   **Evento**: Renta en Madrid, España.
*   **Hora Local**: 15:00 CEST (UTC+2).
*   **Servidor**: AWS Oregon (us-west-2).
*   **Base de Datos**: AWS Oregon o Mexico.

**Análisis**:
1.  **Si se sigue la estrategia UTC Everywhere (Correcto)**:
    *   El frontend envía: `2026-06-15T15:00:00+02:00`.
    *   El backend (Oregon) recibe el ISO.
    *   Convierte a UTC: `2026-06-15T13:00:00Z`.
    *   Guarda en BD: `2026-06-15 13:00:00`.
    *   **Resultado**: **CORRECTO**. La ubicación física del servidor (Oregon, -07:00) es irrelevante porque el OS y la BD operan en UTC.

2.  **Si NO se sigue la estrategia (Error Común)**:
    *   Si el servidor usa hora local (Oregon, -07:00).
    *   Y se guarda `datetime.now()` sin timezone para "created_at".
    *   Se guardaría `06:00 AM` (hora Oregon) mientras que en España son las `15:00 PM`.
    *   Al leerlo en España, parecería que la renta se creó en el pasado o futuro incorrecto.

**Conclusión**:
No hay problema técnico de integridad de datos siempre y cuando **la infraestructura (EC2/RDS) esté forzada a UTC**. La latencia de red entre España y Oregon (~150ms) es el único factor diferenciador, pero no afecta la lógica de fechas.
