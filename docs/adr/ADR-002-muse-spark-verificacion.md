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
      - Solo herramientas permitidas: la lista blanca de v1 está vacía, así que cualquier `tool_call` produce `herramienta_no_permitida`.
   2. **Juez Muse Spark:** revisa que cada afirmación del registro o de la explicación tenga evidencia en el texto o la foto del ciudadano o en los datos entregados. Cualquier `supported=false` produce `afirmacion_sin_evidencia`.
   3. **Reintentos:** hasta 3 intentos en total. Cada intento recibe los motivos del anterior. Tras el tercer fallo, el estado es `requiere_revision_humana`. Cada intento queda registrado (motivos, tokens y latencia).
4. **La confianza la calcula código** (`verification/confidence.py`, función pura y determinista), nunca el modelo:
   - Fuentes de evidencia: (a) grupos de estaciones, (b) IMERG Early en la celda del reporte y (c) el pronóstico vigente.
   - **Las estaciones correlacionadas cuentan como UNA sola fuente.** Se agrupan las que tienen r ≥ 0,8 en el entrenamiento (SUPUESTO; hoy, un grupo de 2 con r = 0,88 [INV]). Cada grupo aporta una señal, igual que cada estación no agrupada, con un peso reducido (SUPUESTO) porque r entre 0,49 y 0,75 sigue siendo dependencia.
   - Puntaje entre 0 y 1 con su desglose por fuente. En v1 los pesos son **SUPUESTO fijos en configuración** (Must). Su calibración con el set de evaluación de reportes es **[Should]** (TASK-021).
5. **Fallback:** con `DEMO_FALLBACK=1` se usan respuestas grabadas que pasan por la misma compuerta y se marcan `fallback=true`.

## Consecuencias
- Costo estimado por intento ≈ US$0,01 (SUPUESTO de tokens; NFR-3); como máximo 3 intentos por reporte.
- La latencia de `POST /reports` es de segundos, así que la API responde `202` y el cliente consulta el estado.
- El juez no reemplaza a las comprobaciones deterministas, que corren primero y gratis.

## Alternativas descartadas
- Confianza calculada por el LLM: no es reproducible ni auditable.
- `max_tokens` bajo para ahorrar: produce respuestas vacías [API].
- Contar cada estación como fuente independiente: infla la confianza en una cuenca corta.
