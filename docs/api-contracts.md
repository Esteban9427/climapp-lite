# Contratos de API — ClimApp Lite

> La fuente de verdad es [`openapi.yaml`](openapi.yaml), OpenAPI 3.1. Este documento resume los contratos y las reglas que no caben en el esquema. Las entidades están detalladas en [`data-model.md`](data-model.md).

| Método y ruta | Propósito | Respuestas | Reglas |
|---------------|-----------|------------|--------|
| `GET /forecast` | Pronóstico vigente para mañana (`replay_date` y `variant` opcionales) | 200 `Forecast` · 422 `historica` sin `replay_date` · 503 sin pronóstico | Siempre incluye `disclaimer`, `official_channels_url`, `data_plan` y `variant`. En vivo solo se publica la variante `operativa`; con `replay_date` la variante por defecto es `historica` (ADR-001 §3). `explanation` solo aparece si pasó la compuerta. `stale=true` si tiene más de 24 h |
| `POST /reports` | Reporte ciudadano (multipart: texto o foto, `lat`, `lon`) | 202 `Report` en estado `verificando` · 422 entrada inválida · 503 `sin_poligono` | Fuera de la cuenca: 202 con `rechazado/fuera_de_cuenca` y sin llamada al LLM. EXIF y metadatos eliminados (se recodifica la imagen). Una foto sin texto pasa a `requiere_revision_humana` sin llamar al modelo (v1 no verifica imágenes). Máximo 3 intentos de verificación (ADR-002). El texto del ciudadano no se publica. Con `DEMO_FALLBACK=1`, solo se verifica un texto con grabación exacta; si no la hay, `requiere_revision_humana` con `review_reason=sin_grabacion` |
| `GET /reports` | Lista y mapa (`status`, `from`, `to`, `limit` ≤ 500) | 200 `ReportSummary[]` · 422 | Solo campos estructurados: tipo de evento, intensidad, hora observada, coordenadas redondeadas a 3 decimales, estado, confianza y `fallback`. **Sin `id` ni `claims`**: desde la lista no se llega al detalle (decisión del equipo, 2026-10-31) |
| `GET /reports/{id}` | Estado y detalle de un reporte (sondeo HTMX) | 200 `Report` · 404 | Incluye las `claims`. Solo lo conoce quien envió el reporte: el id es un UUID4 no adivinable y no aparece en la lista |
| `GET /evaluation` | Métricas del modelo y las líneas base en el periodo apartado (`target_rule`) | 200 `EvaluationReport` · 503 sin evaluación · 422 regla no evaluada | `scenarios.con_est_b` trae el RF por variante (`operativa`, `historica`), calibrado y sin calibrar, y las dos líneas base; la `historica` va con `available_live=false` y su nota. `sin_est_b` vacío hasta TASK-029. `data_plan` activo; `excluded_imputed_days`. `sensitivity` e `imerg_final_vs_early` son [Should] y pueden ser `null` |

## Errores
Formato único `{code, message}`. Nunca se devuelven trazas ni mensajes del proveedor del LLM.

## Contrato con la Meta Model API (saliente)
`POST {META_API_BASE_URL}/chat/completions`, modelo `MUSE_MODEL`, con `reasoning_effort` y `max_tokens` según ADR-002. Una respuesta se acepta solo si `finish_reason == "stop"`, el contenido no está vacío y es JSON válido contra el esquema.
