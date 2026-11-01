# ADR-002: Muse Spark y compuerta de verificación

- **Estado:** Aceptado con SUPUESTOS
- **Fecha:** 2026-10-29
- **Relacionados:** PRD IN 4-6, NFR-2, NFR-3, NFR-6, NFR-9; US-02 a US-04

## Contexto
Muse Spark 1.3 (Meta Model API) convierte el reporte ciudadano en un registro estructurado y explica el pronóstico. Hechos verificados el 2026-10-29 [API]:
- API compatible con el SDK de OpenAI en `https://api.meta.ai/v1`, modelo `muse-spark-1.3`, con soporte de `reasoning_effort`.
- Es un modelo de razonamiento: los tokens de razonamiento consumen `max_tokens` y se cobran como salida. Con `max_tokens=200` devolvió `content=None`.
- Con `reasoning_effort=low` gastó 182 tokens de salida y sin el parámetro, 277.
- Precio: US$1,25 por millón de tokens de entrada y US$4,25 por millón de salida.

La verificación sigue el taller de Meta: comprobaciones deterministas, juez y reintentos.

## Decisión
1. **Cliente:** SDK `openai` con `base_url` y `api_key` desde el entorno (`META_API_BASE_URL`, `META_API_KEY`, `MUSE_MODEL`). Nada hardcodeado.
2. **Parámetros por tarea:**
   | Tarea | `reasoning_effort` | `max_tokens` | Salida |
   |-------|--------------------|--------------|--------|
   | Estructurar el reporte | `low` | 2000 | JSON según `ReportStructured` (data-model) |
   | Explicar el pronóstico | `low` | 2000 | Texto ≤ 600 caracteres + lista de cifras citadas |
   | Juez | `medium` | 2000 | JSON `{claims:[{text, evidence, supported}]}` |
3. **Compuerta, en este orden:**
   1. **Deterministas** (sin LLM, en `verification/checks.py`):
      - `finish_reason == "stop"`; si no, `respuesta_incompleta`.
      - Contenido no vacío ni `None`; si no, `respuesta_vacia`.
      - JSON válido contra el esquema Pydantic; si no, `esquema_invalido`.
      - Cada cifra citada es igual a la calculada por el modelo de pronóstico (probabilidad redondeada a entero en %, acumulado a 1 decimal en mm); si no, `cifra_no_coincide`.
      - **Sin datos personales en las afirmaciones** (decisión del equipo, 2026-10-31): una `claim` con teléfono colombiano (celular 3xx o fijo 60x, con +57 opcional), correo o placa (ABC123, ABC12D) produce `dato_personal`. El prompt de estructuración además pide omitirlos. Va después de las cifras y antes de las herramientas.
      - Solo herramientas permitidas: la lista blanca de v1 está vacía, así que cualquier `tool_call` produce `herramienta_no_permitida`.
   2. **Juez Muse Spark:** revisa que cada afirmación del registro o de la explicación tenga evidencia en el texto o la foto del ciudadano o en los datos entregados. Cualquier `supported=false` produce `afirmacion_sin_evidencia`.
   3. **Reintentos:** hasta 3 intentos en total. Cada intento recibe los motivos del anterior. Tras el tercer fallo, el estado es `requiere_revision_humana`. Cada intento queda registrado (motivos, tokens y latencia).
4. **La confianza la calcula código** (`verification/confidence.py`, función pura y determinista), nunca el modelo:
   - Fuentes de evidencia: (a) grupos de estaciones, (b) IMERG Early en la celda del reporte y (c) el pronóstico vigente.
   - **Las estaciones correlacionadas cuentan como UNA sola fuente.** Se agrupan, como componentes conexas, las que tienen r ≥ 0,8 (SUPUESTO) con al menos `STATION_GROUP_MIN_OVERLAP_DAYS` días comunes (365, SUPUESTO), calculado sobre **toda la tabla diaria** (días válidos y no imputados). **Cambio del 2026-10-31 (decisión del equipo):** antes decía "en el entrenamiento", pero EST-C y EST-D empiezan en 2023, después de `VALID_END`, y con solo el entrenamiento no se podía medir ningún grupo. Los grupos solo afectan la confianza de los reportes, no las métricas del pronóstico. Resultado (TASK-002, `climapp-groups`): [EST-A], [EST-B, EST-C] (r = 0,874; 853 días) y [EST-D]. Cada grupo aporta una señal, igual que cada estación no agrupada, con un peso reducido (SUPUESTO) porque r entre 0,49 y 0,75 sigue siendo dependencia.
   - Puntaje entre 0 y 1 con su desglose por fuente. En v1 los pesos son **SUPUESTO fijos en configuración** (Must). Su calibración con el set de evaluación de reportes es **[Should]** (TASK-021).
   - **Pesos (decisión del equipo, 2026-10-31; SUPUESTO pendiente de JM, PRD SP-15):** cada grupo de estaciones **1,0**, IMERG Early **0,5** y pronóstico vigente **0,25**. Se cuenta como lluvia desde 1 mm ([OMM], PRD SP-2). Razones: las estaciones son la verdad de terreno en la cuenca; el satélite es una celda de 0,1° con r entre 0,46 y 0,64 frente a las estaciones; el pronóstico es una expectativa, no evidencia de lo que pasó. **Se fijaron antes de evaluar la demo** y no se ajustan mirando sus resultados. Un grupo de estaciones pesa más que el satélite y el pronóstico juntos (hay test). El puntaje es la suma de los pesos de las fuentes que concuerdan dividida por la suma de los pesos de las fuentes con dato. Un grupo indica lluvia si alguna de sus estaciones con dato llega a 1 mm; con la media, una estación duplicada podía subir la confianza (TASK-014).
   - **Nivel del río (TASK-039, 2026-11-01):** si el reporte afirma una creciente (`event_type = crecida`), la subida máxima de nivel en 24 h de la serie `LEVEL_SERIES_ID` (EST-A) ese día local (`LEVEL_DAILY_FILE`, ADR-004 §8; si el archivo trae otras series, no cuentan) es una fuente más, `kind = river_level`, **aparte de la lluvia**: mide el río, no la lluvia, así que no se agrupa con las estaciones. Concuerda si la subida llega a `LEVEL_RISE_THRESHOLD_M`. Peso `CONFIDENCE_WEIGHT_LEVEL`. Valores: **1,0 y 0,30 m, SUPUESTO para JM (PRD SP-17), fijados antes de evaluar la demo**. Sin dato de nivel ese día, o si el reporte no afirma creciente, la fuente no aparece y la confianza queda igual (tests de propiedades). Agrega `river_level` al enum `kind` del contrato (`docs/openapi.yaml`).
5. **Fallback:** con `DEMO_FALLBACK=1` se usan respuestas grabadas que pasan por la misma compuerta y se marcan `fallback=true`.
   - **Solo coincidencia exacta (decisión del equipo, 2026-10-31):** una grabación responde únicamente si coinciden la tarea, la **versión del prompt** (hash del prompt de sistema) y el **hash de la entrada** (los mensajes que no son de sistema). Si no coinciden, el cliente **falla cerrado** (`MissingRecordingError`): la explicación queda en `null` y el reporte pasa a `requiere_revision_humana` con `review_reason=sin_grabacion`. Un reporte nunca recibe la respuesta grabada de otro (hay test).
   - Un cambio de prompt invalida las grabaciones de forma explícita: un test exige que cada grabación de `MUSE_FALLBACK_FILE` tenga la versión vigente de su prompt.
   - En modo demo, la hora de recepción que ve el modelo es `DEMO_REPORT_TIME` (la tarde de E1): así el pedido de estructuración es reproducible. Los textos grabados son los ejemplos de `DEMO_REPORTS_FILE`, que la web ofrece como botones solo en modo demo.

## Corridas reales (2026-10-31, `muse-spark-1.3`, US$1,25 por millón de tokens de entrada y US$4,25 por millón de salida)
| Corrida | Qué | Llamadas | Tokens entrada / salida | Costo (US$) | Resultado | Grabación |
|---------|-----|----------|-------------------------|-------------|-----------|-----------|
| 1 | Reporte sintético (estructurar + juez) | 2 | 440 / 1 665 | 0,0076 | `verificado` al primer intento | `config/muse_fallback.json` (fallback de la demo) |
| 1 | Explicación de E1 (`replay_date=2024-12-31`, `historica`) | 6 | 1 647 / 8 226 | 0,0370 | El juez la rechazó en los 3 intentos (`afirmacion_sin_evidencia`) → `explanation=null` | `tests/fixtures/muse/e1_rechazada_2026-10-31.json` (ejemplo de la compuerta bloqueando) |
| 2 | Explicación de E1 con la evidencia corregida | 2 | 804 / 2 723 | 0,0126 | `verificado` al primer intento | `config/muse_fallback.json` (fallback de la demo) |
| 2 | Sonda negativa: explicación que habla de "alerta de creciente", con las cifras correctas | 1 | 400 / 1 833 | 0,0083 | El juez la rechaza (`supported=false`, "sin mención de 'creciente'") | `tests/fixtures/muse/juez_rechaza_alerta.json` |
| 3 | Explicación de E1 con el prompt que pide "%" | 2 | 835 / 2 133 | 0,0101 | `verificado` al primer intento ("un 13 % de probabilidad") | `config/muse_fallback.json`: reemplaza a la grabación de E1 de la corrida 2 |
| 4 | Regrabación con clave exacta: explicación de E1 | 2 | 828 / 3 245 | 0,0148 | `verificado` al primer intento ("13 %") | `config/muse_fallback.json` |
| 4 | Regrabación con clave exacta: 3 reportes de ejemplo de la demo | 6 | 1 325 / 4 221 | 0,0196 | Los 3 `verificado` al primer intento | `config/muse_fallback.json` |
| **Total** | | **21** | **6 279 / 24 046** | **0,1100** | | |

- **Causa del rechazo de la corrida 1:** el juez recibía las cifras con sus claves (`probabilidad_pct: 13`) pero sin su significado, y no encontraba respaldo para "mañana", "cuenca del río Pance" ni "últimos tres días". **Corrección (TASK-022, TDD):** el explicador y el juez reciben la misma evidencia: cada cifra con su significado (probabilidad de ≥ 20 mm mañana en la cuenca, regla `basin_mean`; acumulado de los últimos tres días), la variante, si es una reproducción y que no es una alerta oficial. Al explicador se le prohíbe hablar de crecientes o de alertas.
- En la corrida 4, el primer reporte de ejemplo recibió un `APIConnectionError` sin tokens; el sistema lo cerró como `muse_no_disponible`, como corresponde, y se repitió solo ese reporte. La corrida 4 reemplaza por completo a las grabaciones de las corridas 1 a 3 en `config/muse_fallback.json`; las de `tests/fixtures/muse/` siguen intactas como evidencia histórica.
- En la corrida 2, la primera llamada de la sonda devolvió un error de la API sin tokens registrados; `explain_forecast` la convirtió en `null`, como corresponde. Se repitió solo esa llamada.
- **Tokens:** un intento con juez gasta entre 2 100 y 3 500 tokens de salida, porque el razonamiento consume `max_tokens`. El costo real por intento (≈ US$0,01-0,02) queda cerca del SUPUESTO de NFR-3, y un reporte que agota los 3 intentos cuesta ≈ US$0,04.
- La explicación de la corrida 2 decía "es de 13", sin "%". El prompt ahora pide el símbolo, y un test lo exige en la grabación de la demo (corrida 3).

## Consecuencias
- Costo estimado por intento ≈ US$0,01 (SUPUESTO de tokens; NFR-3); como máximo 3 intentos por reporte.
- La latencia de `POST /reports` es de segundos, así que la API responde `202` y el cliente consulta el estado.
- El juez no reemplaza a las comprobaciones deterministas, que corren primero y gratis.

## Alternativas descartadas
- Confianza calculada por el LLM: no es reproducible ni auditable.
- `max_tokens` bajo para ahorrar: produce respuestas vacías [API].
- Contar cada estación como fuente independiente: infla la confianza en una cuenca corta.
