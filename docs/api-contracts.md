# Contratos de API — ClimApp Lite

> La fuente de verdad es [`openapi.yaml`](openapi.yaml), OpenAPI 3.1. Este documento resume los contratos y las reglas que no caben en el esquema. Las entidades están detalladas en [`data-model.md`](data-model.md).

| Método y ruta | Propósito | Respuestas | Reglas |
|---------------|-----------|------------|--------|
| `GET /forecast` | Pronóstico vigente para mañana (`variant=full\|operational`, `replay_date` opcional) | 200 `Forecast` · 503 sin pronóstico | Siempre incluye `disclaimer` y `official_channels_url`. `explanation` solo aparece si pasó la compuerta. `stale=true` si tiene más de 24 h |
| `POST /reports` | Reporte ciudadano (multipart: texto o foto, `lat`, `lon`) | 202 `Report` en estado `verificando` · 422 entrada inválida | Fuera de la cuenca: 202 con `rechazado/fuera_de_cuenca` y sin llamada al LLM. EXIF eliminado. Máximo 3 intentos de verificación (ADR-002) |
| `GET /reports` | Lista para el mapa (`status`, `from`, `to`, `limit` ≤ 500) | 200 `Report[]` | Coordenadas publicadas redondeadas a 3 decimales |
| `GET /reports/{id}` | Estado de un reporte (sondeo HTMX) | 200 `Report` · 404 | — |
| `GET /evaluation` | Métricas del modelo y las líneas base en el periodo apartado (`target_rule`) | 200 `EvaluationReport` | Incluye `rf_operational` (R11), el sesgo Final↔Early y `excluded_imputed_days` |

## Errores
Formato único `{code, message}`. Nunca se devuelven trazas ni mensajes del proveedor del LLM.

## Contrato con la Meta Model API (saliente)
`POST {META_API_BASE_URL}/chat/completions`, modelo `MUSE_MODEL`, con `reasoning_effort` y `max_tokens` según ADR-002. Una respuesta se acepta solo si `finish_reason == "stop"`, el contenido no está vacío y es JSON válido contra el esquema.
