# Revisión de Muse Code — día 3c (2026-11-01, cierre del domingo)

> **Comando:** `muse exec --model muse-spark-1.3 --contributor-mode off --effort medium "Revisa en solo lectura lo construido el 2026-11-01 […] Busca sobre todo BUGS […] Separa claramente bugs de mejoras. No edites nada."` (pedido completo en la sesión).
> **Versión:** Muse Code 1.4.14. **Commit revisado:** `9c1fe90` (todo el 2026-11-01: TASK-038/039, 009b, ajustes de UI, contexto del pronóstico, fallback, duplicados).
> **Entorno:** copia de `git ls-files` (sin `data/`, `.env` ni `.forbidden-terms`). Workspace no confiable: `CLAUDE.md` se leyó como documento. Sin git ni `uv` en la copia.
> **Solo lectura:** `diff -rq` contra una copia de control (excluyendo cachés), sin diferencias.

## Cómo se atendió (solo se corrigen bugs; lo demás queda anotado)
| # | Hallazgo | Decisión | Evidencia |
|---|----------|----------|-----------|
| 1 | `log.info(..., latest=date)` rompería el log JSON | **Corregido, y era más grave**: los loggers de módulo se creaban al importar y **nunca emitían JSON** (salían en formato de consola). `get_logger` ahora es perezoso (campo `module`) y `JSONRenderer(default=str)` | `34ed421` (rojo) → `2c0eb67`; `climapp-imerg` termina con un evento JSON |
| 2 | La caché del explicador ignoraba las cifras | **Corregido**: la clave suma las cifras y el riesgo | `7001bf0` → `32710b1` |
| 10 | "20 mm" escrito a mano en el significado de la climatología | **Corregido**: usa `FORECAST_THRESHOLD_MM`. Con 20 mm el pedido no cambia y las grabaciones siguen coincidiendo | `7001bf0` → `32710b1` |
| 8 | Duplicado revisado antes de la cuenca y sin ubicación | **Corregido**: se revisa tras la cuenca y exige la misma ubicación publicada. La carrera entre dos POST simultáneos queda anotada | `0fd4d50` → `f67c073` |
| 4 | El contrato decía `historica` por defecto con `replay_date` | **Corregido** en `docs/openapi.yaml` | este commit |
| 3 | La evidencia toma `probs[0]` y la API la emisión más reciente | No es bug hoy: hay una sola emisión por día objetivo y variante | — |
| 5 | `ReportIn.observed_at` en el contrato, pero `POST /reports` no lo acepta | Anotado (anterior a hoy; decisión de contrato para el lunes) | — |
| 6 | Estructurar exige `numbers_cited` vacío: un reporte con dígitos ("subió 5 metros") va a revisión humana | Anotado (diseño de ADR-002 §3, anterior a hoy). Importante para la evaluación de TASK-021/036 con los reportes de JM | — |
| 7 | Fallback cíclico con contador global | Anotado y ya documentado en ADR-002 §5: demo de un solo usuario | — |
| 9 | Orden de índices lon/lat en OPeNDAP sin confirmar | **No es bug**: la DDS real de GES DISC es `precipitation[time = 1][lon = 3600][lat = 1800]`, y la respuesta devuelve la celda lat 3,35 / lon −76,65, que contiene el centro de la cuenca | DDS consultada el 2026-11-01 |
| — | Bordes menores (`_rows` de hojas 2+, el mapa relee los CSV por marcador, `_outcome` ignora `daily_variant`, `n ≤ 3` en el contrato) y mejoras (dimensiones de fotos, claves `id(settings)`, `PERCENT` duplicado) | Anotados para después del congelamiento | — |

## Salida (rutas absolutas de la copia reemplazadas por rutas del repo; sin las líneas de arranque del CLI)

# Revisión de solo lectura — lo construido el 2026-11-01

No edité nada. Leí `level.py`, `confidence.py`, `evidence.py`, `imerg.py`, `context.py`, `forecast_routes.py`, `explain.py`, `schemas.py`, `formatting.py`, `muse.py`, `reports.py`, `store.py`, `demo_reset.py`, `web/`, tests, `docs/openapi.yaml`, ADR-001/002/004, PRD, `design.md`, `CLAUDE.md` y `docs/dod.md`.

## Veredictos rápidos (verificado)

- **Nivel / IMERG en el modelo: no entran.** `forecast/features.py` solo usa estaciones + CHIRPS; `grep` de `imerg|level|nivel` en `forecast/` y `data/daily.py` da cero. Coherente con ADR-001/004.
- **Confianza calculada por el LLM: no.** `reports.py:_outcome` usa `compute_confidence` en código; el LLM nunca toca el puntaje. Coherente con CLAUDE.md regla 8.
- **Fallback devuelve respuesta de otro pedido: no**, salvo concurrencia (bug 7). Clave exacta por `(tarea, versión de prompt, hash de entrada)` + fallo cerrado. Bien.
- **XSS en web/popups: no encontrado.** Jinja2 con autoescape en todas las plantillas; `map.js` construye popups con `textContent`; `map_data` va por `tojson`. El único `innerHTML`-adjacent es la atribución de Leaflet, con datos de configuración del operador (URL validada a `http(s)` en `config.py`), no input de usuario.
- **Inyección SQL: no.** `store.py` parametriza todos los valores; el `f-string` solo interpola cláusulas fijas. El `noqa: S608` está justificado.
- **Nombres/coordenadas de estaciones: no encontrados.** Solo `EST-A…EST-D` y posiciones (`alta/media/piedemonte`), como exige ADR-004. `CVC` aparece como titular de datos autorizado (D-03), no como estación. `DEMO_EXAMPLE_LAT/LON` y el rectángulo del ADR son puntos del cauce OSM, no estaciones, según los propios docs. Ojo: `.forbidden-terms` no existe en este snapshot, así que el DoD §7 no es verificable aquí.

## Bugs (ordenados por gravedad)

| # | Zona | Fallo en una frase |
|---|---|---|
| 1 | `imerg.py:215` | `latest=date` a structlog JSONrevienta |
| 2 | `explain.py:147` | Caché ignora las cifras |
| 3 | `evidence.py:99` | Evidencia usa `probs[0]`, API el más reciente |
| 4 | `openapi.yaml:18` | Contrato dice `historica` por defecto |
| 5 | `openapi.yaml:199` | Contrato promete `observed_at` que se ignora |
| 6 | `reports.py:49` | Reporte con dígitos nunca se verifica |
| 7 | `muse.py:230` | Fallback cíclico + contador global |
| 8 | `reports.py:151` | Duplicados con carrera y sin ubicación |
| 9 | `imerg.py:137` | Orden de índices lon/lat por confirmar |
| 10 | `explain.py:77` | Umbral y regla hardcodeados en texto |

1. **`log.info("imerg.written", latest=date)` crashea.** `logging.py` usa `JSONRenderer()` sin serializador propio y `json.dumps` no acepta `date`. Con caché no vacía, `climapp-imerg` cae justo al final, después de escribir el CSV.
2. **`_CachedExplainer` no incluye cifras en la clave.** Clave `(target_date, variant, model_version, replay)` sin `prob`, `accum_3d_mm`, umbral ni climatología. Si el pronóstico se republica con otros números, devuelve la explicación vieja sin pasar la compuerta: las cifras citadas ya no coincidirían.
3. **Evidencia vs API usan pronósticos distintos.** `evidence._forecast` toma `probs[0]` (orden de archivo) y `artifacts.find_forecast` el `max(issue_date)`. Con varias emisiones para el mismo día, la confianza se calcula con una probabilidad y el riesgo publicado con otra.
4. **Contrato desactualizado: variante por defecto.** `docs/openapi.yaml:18-22` dice que con `replay_date` el defecto es `historica`; el código (`forecast_routes.py:142`) usa `operativa` siempre, como decidió ADR-001 §3 el 2026-11-01. El test `test_replay_defaults_to_the_operational_variant` fija el código. Hay que actualizar el YAML, no el código.
5. **Contrato promete `observed_at` en `ReportIn`.** `openapi.yaml:199` lo lista, pero `POST /reports` no lo acepta: un cliente que lo envíe lo pierde en silencio y la hora observada la inventa el LLM (`hora_de_recepcion`).
6. **Estructurar exige `numbers_cited` vacío.** `allowed_numbers=frozenset()` + prompt "lista vacía". Un reporte legítimo con dígitos ("hace 2 horas", "subió 5 metros") falla con `cifra_no_coincide` en los 3 intentos y termina en revisión humana. Los textos de la demo lo evitan escribiendo los números en palabras, lo que confirma el sesgo.
7. **Fallback cíclico con contador global.** `RecordedMuseClient._next` envuelve con módulo: un 4.º intento del juez o una segunda verificación del mismo texto recibe una grabación de otro intento. El contador es del cliente, no de la verificación: dos POST simultáneos del mismo texto alternan respuestas. El propio ADR-002 lo admite para la demo monousuario; fuera de ella es fuga entre pedidos.
8. **Duplicados: carrera y sin ubicación.** Sin restricción única en SQLite, dos POST simultáneos del mismo texto crean dos reportes. Además el duplicado ignora `lat/lon/foto`, se revisa antes que la cuenca (un texto duplicado desde fuera devuelve el reporte original de dentro) y devuelve el estado viejo (`verificando`) aunque el original ya cambió.
9. **Orden de índices OPeNDAP sin confirmar.** `cell=(lon_idx, lat_idx)` y la URL pide `precipitation[0][lon][lat]`; las mallas GPM suelen ser `(time, lat, lon)`. Si es así, se lee otra celda en silencio. El mock solo verifica el string, no el orden real. Requiere una petición contra GES DISC para cerrar.
10. **Texto de explicación hardcodeado.** `explain.py:77` escribe "20 mm o más" y `:87` "lluvia media de las estaciones" aunque `FORECAST_THRESHOLD_MM` y `TARGET_RULE` son configuración. La compuerta solo revisa números, así que un cambio de config deja texto falso que pasa la verificación.

Bordes menores (bugs pequeños, mismo párrafo cada uno): `_rows` en `level.py:81` solo valida el encabezado de la primera hoja y los números de fila reinician por hoja; `map.py:_marker` relee los 4 CSV por cada marcador; `map.py:_outcome` ignora `daily_variant`; `openapi.yaml:217` limita `n` a 3 pero `VERIFY_MAX_ATTEMPTS` no tiene tope; el mensaje "10 min" está literal en el test y en `design.md` aunque la ventana es configuración.

## Mejoras (no son bugs)

- Límite de dimensiones en fotos (bomba de descompresión: 5 MB comprimidos no acotan píxeles).
- `_EXPLAINERS`/`_CLIENTS` con clave `id(settings)`: crece con cada settings de tests y reusa ids tras GC. Usar la propia instancia como clave o `WeakValueDictionary`.
- `es_number(-0.0)` puede dar `"-0"`; irrelevante hoy porque las entradas son ≥ 0.
- `PERCENT = 100` duplicado en 4 módulos; `MAX_TEXT_CHARS` duplica el contrato. Centralizar.

## Contraste CLAUDE.md / DoD

Cumple: confianza en código, compuerta sin saltos, sin `print`/`except Exception` vistos en lo leído, sin secretos ni datos en git, `EST-x` en todo. Incumple parcial: regla 2 — el "20 mm" y `basin_mean` del punto 10 son umbrales en código fuera de configuración; DoD §7 no verificable sin `.forbidden-terms`; DoD §9 falla por los puntos 4 y 5 (el test de contrato valida respuestas, no los parámetros de entrada `variant`/`observed_at`).
