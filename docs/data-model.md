# Modelo de datos — ClimApp Lite

> Entidades como modelos Pydantic v2 (`src/climapp/*/models.py`). En v1 la persistencia es SQLite en `DATA_DIR/climapp.db`, fuera de git. Las horas van en ISO 8601 con zona; los días, en fecha local America/Bogota (ADR-004).

## Datos de entrada (derivados, no versionados)
### DailyPrecip — tabla diaria regenerada con TDD
| Campo | Tipo | Regla |
|-------|------|-------|
| `date` | date | Día local. Estaciones: la lectura de las 00:00 cierra el día anterior (cada lectura cierra el paso de 10 min que termina en su instante) |
| `series_id` | str | `EST-A`…`EST-D`, `IMERG_E` (serie principal), `IMERG_F` (solo contraste), `CHIRPS_598`…`CHIRPS_600` |
| `precip_mm` | float \| null | null si el día no es válido |
| `n_readings` | int \| null | Solo estaciones (máx. 144) |
| `valid` | bool | Estaciones: `n_readings ≥ 100` (SUPUESTO) |
| `imputed` | bool | `true` si se rellenó con vecinas; **excluido de la evaluación** |
| `source_hash` | str | SHA-256 de los archivos crudos de origen del día, separados por coma (la unión de exportaciones puede aportar dos); vacío si el día no tiene lecturas |
| `n_suspect` | int | Saltos `suspect` del día (SP-12 [JM 2026-10-30]): salto ≥ `SUSPECT_STEP_MM` tras lecturas regulares con el contador quieto |
| `suspect_mm` | float | Lluvia de esos saltos; **no** se suma a `precip_mm`, se conserva para auditoría |
| `n_gap` | int | Pasos sobre huecos > `MAX_GAP_MIN`: si cruzan el día local no suman lluvia (`GAP`); si no, la conservan (`GAP_INTRADAY`). ADR-004 §2, PRD SP-14 |

### DailyLevel — serie diaria de nivel del río (TASK-038, ADR-004 §8)
Solo evidencia de crecientes en la confianza (TASK-039); no entra al modelo.

| Campo | Tipo | Regla |
|-------|------|-------|
| `series_id` | str | `EST-A` (estación de la parte media) |
| `date` | date | Día local |
| `n_readings` | int | Lecturas con valor en el día (una cada 15 min) |
| `level_min_m`, `level_max_m` | float | Nivel mínimo y máximo del día, en m |
| `rise_24h_max_m` | float | Máximo, sobre las lecturas del día, de su nivel menos el mínimo de las 24 h anteriores; ≥ 0 |

## Pronóstico
### Forecast (`GET /forecast`)
| Campo | Tipo | Nota |
|-------|------|------|
| `issued_at` | datetime | Momento del cálculo |
| `target_date` | date | Mañana |
| `prob_ge_threshold` | float [0, 1] | Probabilidad del modelo |
| `threshold_mm` | float | 20.0 (SUPUESTO; `FORECAST_THRESHOLD_MM`) |
| `target_rule` | enum `any_station` \| `basin_mean` \| `reference_station` | ADR-001; por defecto `basin_mean` |
| `accum_3d_mm` | float \| null | Suma de los últimos 3 días válidos |
| `accum_3d_level` | enum `normal` \| `elevado` | `elevado` si ≥ `ACCUM3_THRESHOLD_MM` (100, SUPUESTO) |
| `data_plan` | enum `principal` \| `plan_b_earthdata` \| `plan_b_datos` | Plan de datos activo (ADR-001 §5, ADR-004 §5) |
| `variant` | enum `operativa` \| `historica` | `operativa` en vivo; `historica` (con CHIRPS, semanas de retraso) solo en reproducción (ADR-001 §3) |
| `model_version` | str | Hash de datos y parámetros |
| `explanation` | str \| null | Texto de Muse Spark **verificado**; null si no pasó la compuerta |
| `explanation_fallback` | bool | `true` si la explicación viene de respuestas grabadas (`DEMO_FALLBACK=1`, ADR-002 §5) |
| `inputs_available` | list[str] | Series con dato para el día de emisión |
| `stale` | bool | `true` si `issued_at` tiene más de 24 h |
| `replay` | bool | `true` en reproducción histórica |
| `disclaimer` | str | Siempre presente: "No es una alerta oficial…" |
| `official_channels_url` | str | `OFFICIAL_CHANNELS_URL` |

## Reportes
### ReportIn (`POST /reports`, multipart)
| Campo | Tipo | Regla |
|-------|------|-------|
| `text` | str (1-1000) | Obligatorio si no hay foto |
| `photo` | imagen JPEG/PNG ≤ 5 MB | Se elimina el EXIF al recibirla |
| `lat`, `lon` | float | Debe caer dentro del polígono de la cuenca; si no, `fuera_de_cuenca` |
| `observed_at` | datetime \| null | Si es null, se usa la hora de recepción |

### ReportStructured (salida de Muse Spark validada por esquema)
| Campo | Tipo |
|-------|------|
| `event_type` | enum `lluvia` \| `crecida` \| `deslizamiento` \| `granizo` \| `sin_lluvia` \| `otro` |
| `intensity` | enum `ninguna` \| `debil` \| `moderada` \| `fuerte` (descriptiva; las categorías no tienen fuente IDEAM/OMM, SUPUESTO) |
| `observed_at` | datetime |
| `claims` | list[str]: afirmaciones atómicas que revisa el juez |
| `numbers_cited` | list[float]: deben coincidir con las cifras del sistema |

### ReportSummary (`GET /reports`, lista y mapa)
Sin `id`, texto ni afirmaciones (decisión del equipo, 2026-10-31): desde la lista no se llega al detalle.

| Campo | Tipo | Nota |
|-------|------|------|
| `event_type` | enum \| null | De `structured`; null si no está verificado |
| `intensity` | enum \| null | De `structured` |
| `observed_at` | datetime \| null | De `structured` |
| `lat`, `lon` | float | Redondeados a 3 decimales (~100 m) |
| `status` | enum | Igual que en `Report` |
| `confidence` | Confidence \| null | Solo si `verificado` |
| `fallback` | bool | Respuesta grabada (`DEMO_FALLBACK=1`) |

### Report (`POST /reports`, `GET /reports/{id}`)
Detalle para quien envió el reporte (id UUID4 no adivinable): incluye `structured.claims`. El texto del ciudadano nunca se publica.
| Campo | Tipo | Nota |
|-------|------|------|
| `id` | UUID | |
| `received_at` | datetime | |
| `lat`, `lon` | float | Redondeados a 3 decimales (~100 m) al publicarlos (privacidad) |
| `status` | enum `verificando` \| `verificado` \| `rechazado` \| `requiere_revision_humana` | |
| `reject_reason` | enum \| null | `fuera_de_cuenca`, `entrada_invalida` |
| `review_reason` | enum \| null | Por qué fue a revisión humana sin pasar por la compuerta: `solo_foto`, `muse_no_disponible` o `sin_grabacion` (demo sin grabación exacta, ADR-002 §5) |
| `structured` | ReportStructured \| null | Solo si `verificado` |
| `confidence` | Confidence \| null | Solo si `verificado` |
| `attempts` | list[VerificationAttempt] | Historial completo |
| `fallback` | bool | Respuesta grabada (`DEMO_FALLBACK=1`) |

### VerificationAttempt
| Campo | Tipo |
|-------|------|
| `n` | int (1-3) |
| `passed` | bool |
| `reasons` | list[enum]: `respuesta_incompleta`, `respuesta_vacia`, `esquema_invalido`, `cifra_no_coincide`, `dato_personal`, `herramienta_no_permitida`, `afirmacion_sin_evidencia` |
| `finish_reason` | str |
| `tokens_in`, `tokens_out` | int |
| `latency_ms` | int |

### Confidence (calculada por código, ADR-002)
| Campo | Tipo |
|-------|------|
| `score` | float [0, 1] |
| `sources` | list[{`source_id`, `kind`: `station_group` \| `satellite` \| `forecast` \| `river_level`, `members`: list[str], `agrees`: bool, `weight`: float}] |
| `independent_sources` | int: número de fuentes con dato; cada grupo de estaciones correlacionadas cuenta una vez (no cada estación), más IMERG Early y el pronóstico |

## Evaluación
### EvaluationReport (`GET /evaluation`)
| Campo | Tipo |
|-------|------|
| `test_period` | {`start`, `end`} |
| `target_rule` | enum (principal: `basin_mean`) |
| `threshold_mm` | float (20, SUPUESTO) |
| `data_plan` | enum |
| `scenarios` | {`con_est_b`, `sin_est_b`}: cada uno list[ModelMetrics] |
| ModelMetrics | {`name`: `rf` \| `climatology` \| `persistence`, `variant`, `calibrated`, `available_live`, `note` (solo rf), `pod`, `far`, `csi`, `brier`, `auc`, `threshold`, `n_days`, `reliability`: list[{`bin`, `forecast`, `observed`, `n`}]} |
| `sensitivity` | **[Should]** list[{`threshold_mm` ∈ {10, 20, 50}, `target_rule`, `event_frequency`, `rf_auc`, `rf_brier`, `climatology_brier`}] \| null |
| `imerg_final_vs_early` | **[Should]** {`period`, `bias_mm`, `pearson_r`, `n_days`} \| null |
| `daily` | list[{`date`, `prob`, `observed`: bool \| null, `outcome`: `acierto` \| `falsa_alarma` \| `fallo` \| `correcto_negativo`}] (para el mapa) |
| `daily_variant` | enum: variante del RF calibrado con la que se calcula `daily` (`operativa`) |
| `excluded_imputed_days` | int |
