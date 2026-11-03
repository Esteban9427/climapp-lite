# Set de evaluación de reportes ciudadanos (TASK-021)

**Paso 1, sin LLM:** `spec_reportes.jsonl` especifica 50 reportes simulados. Cada fila trae el día, la hora, el sector, los hechos del día, la etiqueta esperada y la instrucción para quien escriba el texto. Los textos se escriben en el paso 2, a partir de `instruccion_texto` y sin cambiar ningún otro campo. **La etiqueta sale solo de los datos**, con la regla de abajo. Ningún modelo la decide.

```bash
# claves EVAL_* de eval-harness/.env.example en el .env de la raíz
uv run python eval-harness/build_spec.py      # escribe EVAL_OUTPUT (determinista con EVAL_SEED)
uv run pytest tests/eval_harness
```

## Fuentes de los hechos
| Campo de `hechos` | Fuente | Regla |
|-------------------|--------|-------|
| `lluvia_media_cuenca_mm` | `DAILY_STATIONS_FILE` | Media de las estaciones válidas y no imputadas del día local (`basin_mean`, la misma de `climapp.forecast.target`) |
| `estaciones_con_dato` | ídem | Estaciones que entran en esa media |
| `subida_nivel_24h_m` | `LEVEL_DAILY_FILE`, serie `LEVEL_SERIES_ID` | Subida máxima en 24 h del día local (ADR-004 §8) |
| `imerg_early_mm` | `IMERG_EARLY_FILE` | `null` si no hay dato ese día (la serie empieza el 2026-09-17) |
| `dia_de_evento_de_nivel` | `EVAL_EVENTS_FILE` | El día cae en la ventana de un evento de la tabla de eventos de nivel (entrega 2026-11-01; el nombre real del archivo solo vive en `.env`) |

**Periodo:** el de prueba de ADR-001, `VALID_END` < día ≤ `TEST_END` (2023-01-01 → 2026-10-31). **No entran los días de la demo:** `DEMO_REPLAY_DATE` (2026-10-01), el día de `DEMO_REPORT_TIME` (2026-10-02) y la ventana completa del evento que los contiene (2026-09-30 → 2026-10-02), porque es la misma tormenta.

## Regla de la etiqueta esperada
| Umbral | Valor | Fuente |
|--------|-------|--------|
| Lluvia de un día de evento | `FORECAST_THRESHOLD_MM` = 20 mm | PRD **SP-10**, cerrado [JM 2026-11-01] |
| Subida de un día de evento | `LEVEL_RISE_THRESHOLD_M` = 0,30 m en 24 h | PRD **SP-17**, **SUPUESTO abierto** |
| Día con lluvia | `RAIN_DAY_MM` = 1 mm | [OMM], PRD SP-2 |
| Subida de un día seco | `EVAL_DRY_RISE_M` = 0,05 m | **SUPUESTO** de esta especificación (TASK-021) |
| Exageración | subida afirmada (`EVAL_CLAIMED_RISE_M` = 5 m) mayor que el doble de la observada | **SUPUESTO** (factor 2) |

- **Día de evento:** lluvia media ≥ 20 mm **o** subida ≥ 0,30 m, y en ambos casos lluvia media ≥ 1 mm. Se exige algo de lluvia porque hay días con subida de 0,7 m y 0 mm (lecturas de nivel dudosas, SP-18).
- **Día seco:** lluvia media < 1 mm **y** subida conocida < 0,05 m. Sin dato de nivel, el día no es seco.

| Clase (`clase`) | Días | `etiqueta_esperada` | Si los datos no lo respaldan |
|-----------------|------|---------------------|------------------------------|
| `coherente` (25) | de evento; primero los de la tabla de eventos de nivel | `verdadero` | la fila no se genera (`SpecError`) |
| `dificil` (5) | de evento con lluvia ≥ 20 mm **y** subida ≥ 0,30 m | `verdadero` | ídem |
| `exagerado` (10) | los mismos días de 10 coherentes, con subida observada < 2,5 m | `exagerado` | ídem |
| `falso` (10) | secos | `falso` | ídem |

**Cómo se lee contra la salida del sistema** (lo mide el paso 3, no esta especificación):

| Etiqueta | Acierto | Error |
|----------|---------|-------|
| `verdadero` | `verificado` y confianza ≥ `AGREEMENT_HIGH` | `requiere_revision_humana` es un falso negativo (costo, no riesgo); confianza < `AGREEMENT_LOW` es un error |
| `exagerado` | `requiere_revision_humana` | `verificado` |
| `falso` | `requiere_revision_humana`, o `verificado` con confianza < `AGREEMENT_LOW` | `verificado` con confianza ≥ `AGREEMENT_LOW` |

Las filas `dificil` miden si una cifra plausible ("subió como medio metro") manda un reporte verdadero a revisión humana: hoy `numbers_cited` no vacío lo hace (revisión del día 3c, punto 6). La subida citada sale del dato del día (redondeada a 10 cm o "medio metro" si está a ±7 cm de 0,5 m). La duración de la lluvia ("unas 3 horas") no se puede verificar con datos diarios, así que no cambia la etiqueta.

## Selección (determinista)
Con `EVAL_SEED` y los mismos datos, la salida es idéntica (hay test). Primero se eligen los 5 difíciles, luego los 25 coherentes entre los días de evento restantes, los 10 exagerados entre esos coherentes y los 10 falsos entre los secos. Cada grupo se reparte por año (2023 a 2026, por turnos) y prefiere los días de la tabla de eventos de nivel (salvo los difíciles, que prefieren días fuera de ella, para no repetir tormentas).

- **Hora local:** 30 min después del pico del evento si el reporte cae ese día (salvo los exagerados); si no, una hora de la tarde (14:00 a 19:50, cada 10 min) sorteada.
- **Sector** (`EVAL_SECTORS`): las posiciones de ADR-004 (`alta`, `media-alta`, `media`, `piedemonte`) o un lugar público de OpenStreetMap sobre el río (La Vorágine). Nunca nombres ni coordenadas de estaciones. La especificación no trae coordenadas: la confianza no depende del punto (estaciones de toda la cuenca y una sola celda IMERG, ADR-002 §4), así que el paso 3 puede usar `DEMO_EXAMPLE_LAT`/`LON` para todos los reportes.
- **Instrucción** (`instruccion_texto`): qué afirma el ciudadano. Los coherentes no dan cifras y solo hablan de creciente si la subida llega a 0,30 m; los exagerados afirman 5 m y casas arrasadas; los falsos afirman lluvia fuerte o creciente.

## Paso 2: textos (`reportes_simulados.jsonl`)
**Los textos los generó Muse Spark 1.3, en el nivel Contributor por error, vía opencode** (herramienta previa al evento), a partir de esta especificación, que se deriva de los datos; no son reportes reales. El nivel Contributor era el modelo por defecto de opencode: es el incidente D-07 del 2026-11-02 (se envió solo la spec, sin nombres ni coordenadas de estaciones), y opencode ya usa `muse-spark-1.3` estándar. Cada fila es la de la spec más el campo `texto`, que empieza con "Reporte simulado:". Validación del 2026-11-02, sin LLM: 50 filas, todos los campos de la spec intactos, prefijo en todas, 0 datos personales (la misma comprobación `dato_personal` de la compuerta) y 0 términos de `.forbidden-terms`. La etiqueta sigue siendo la de la spec: **las etiquetas salen de los datos**, no del LLM.

**Limitación:** el generador de los textos y el evaluador (la compuerta y el juez) son de la misma familia de modelos (Muse Spark 1.3). Los textos pueden estar escritos de una forma que a Muse le resulte fácil de interpretar, así que las tasas medidas pueden ser optimistas frente a reportes ciudadanos reales.

## Criterio de elección del esfuerzo del juez: medium vs. high (TASK-036)
Fijado el 2026-11-03, **antes de abrir los resultados** de `v2_s-low_j-high` (el hash de este commit lo prueba). Ambas corridas usan el código v2 y estructuración low.

1. **Obligatorio:** 0 reportes `exagerado` y 0 `falso` verificados (es decir, ninguno en `coincide` ni `parcial`; un `falso` en `no_coincide` es acierto según la tabla de arriba).
2. **Si ambos cumplen:** gana el de menor US$/reporte y menor latencia p50, **salvo** que high supere a medium en **más de 10 puntos porcentuales** de acierto dentro de 3 intentos. Con n = 50 y una sola corrida, una diferencia menor se considera ruido.
3. Si solo uno cumple el punto 1, gana ese. Si ninguno cumple, se queda medium (el valor vigente) y se reporta como fallo.
4. Si medium gana en costo y high en latencia (o al revés), decide el costo (NFR-3).

## Pendiente
- Paso 3: correr la compuerta y medir la tasa de aprobación, el costo por reporte (NFR-3) y la latencia (NFR-2).
- **Nota sobre la regla 9 del repositorio:** la especificación versiona, para 50 días, agregados diarios derivados de los datos (lluvia media, subida e IMERG), sin estaciones ni coordenadas. Es el entregable de TASK-021 en `eval-harness/`; si el equipo prefiere no versionarlos, se regenera con `build_spec.py` desde `DATA_DIR`.
