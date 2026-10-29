# Alcance del MVP — ClimApp Lite

> Congelamiento de alcance: `SCOPE_FREEZE_DATE` (2026-11-02). Desde esa fecha solo entran bugfix, estabilidad de la demo y material de entrega. Todo lo nuevo va a `## OUT`.

## IN
- Pronóstico diario de probabilidad de ≥20 mm para mañana en la cuenca del río Pance, entrenado con la misma serie satelital que existe en operación (IMERG Early).
- Indicador de acumulado de 3 días como señal descriptiva de riesgo de derrumbe.
- Evaluación pública contra climatología y persistencia en el periodo apartado, con y sin EST-B (regla principal `basin_mean`; las sensibilidades de umbral y regla y el contraste Early↔Final son Should).
- Reporte ciudadano con texto o foto (EXIF eliminado), ubicación y hora.
- Muse Spark 1.3: estructuración del reporte y explicación del pronóstico.
- Compuerta de verificación: comprobaciones deterministas, juez, 3 intentos y revisión humana.
- Confianza calculada por código, con estaciones correlacionadas agrupadas.
- Web móvil: pronóstico con explicación verificada, formulario, lista de reportes y mapa mínimo con marcadores (el pulido del mapa es Should).
- Aviso "No es una alerta oficial" con enlace a canales oficiales en cada vista.
- Demo como reproducción histórica con `DEMO_FALLBACK=1`.

## OUT
- Sequía e incendios
- Audio
- Cuentas de usuario
- Notificaciones
- App nativa
- Plataforma de consulta histórica
- Usuarios investigadores
- Reentrenamiento automático
- Datos en vivo de estaciones (la demo es una reproducción histórica)
- Moderación de contenido más allá de la compuerta de verificación
