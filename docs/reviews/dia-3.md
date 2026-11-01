# Revisión de Muse Code — día 3 (2026-11-01)

> **Comando:** `muse exec --model muse-spark-1.3 --contributor-mode off --effort medium "Revisa en solo lectura lo construido hoy (commits c927ee3..d70784c): src/climapp/data/level.py y tests/data/test_level.py (TASK-038), y los cambios de src/climapp/verification/confidence.py, src/climapp/verification/evidence.py, src/climapp/api/reports.py, src/climapp/config.py y sus tests (TASK-039), contra CLAUDE.md, docs/dod.md, docs/adr/ADR-002-muse-spark-verificacion.md §4, docs/adr/ADR-004-datos.md §8, docs/data-model.md y docs/openapi.yaml. Busca: errores en la subida máxima en 24 h (bordes de la ventana, medianoche, marcas repetidas, zona horaria de celdas de fecha), que el nivel pueda cambiar la confianza de un reporte que no afirma creciente o de un día sin nivel, que el nivel pueda entrar al modelo, discrepancias con el contrato y nombres de estaciones en código o docs. No edites nada."`
> **Versión:** Muse Code 1.4.14. **Commit revisado:** `d70784c` (TASK-038 y TASK-039).
> **Entorno:** copia de `git ls-files` (sin `data/`, `.env` ni `.forbidden-terms`). El workspace no era de confianza: Muse leyó `CLAUDE.md` como documento, no como reglas propias. Sin git en la copia: no verificó historial, suite, cobertura ni linters.
> **Solo lectura:** `diff -rq` contra una copia de control (excluyendo cachés), sin diferencias.

## Cómo se atendió
| Hallazgo | Decisión | Evidencia |
|----------|----------|-----------|
| `_level_rise` toma el máximo de todas las series del día; con dos series podría inflar acuerdos | **Corregido** | `LEVEL_SERIES_ID` (EST-A) en la configuración; la evidencia filtra por serie. `7f6f617` (rojo) → fix |
| El borde exacto de 24 h no tiene test | **Corregido** | Test de ventana cerrada (la lectura de hace exactamente 24 h cuenta). `62ee541` |
| `RAW = "ESTACION SINTETICA"` rompe la convención `raw-a` | **Corregido** | `62ee541` |
| Filas con menos de 4 columnas se omiten en silencio | Se mantiene | openpyxl rellena cada fila al ancho de la hoja: una fila corta llega con el valor en `None` y se trata como vacía, igual que el lector de estaciones. Una hoja con menos de 4 columnas falla en el encabezado |
| Las hojas 2+ no validan su encabezado | Se mantiene | Su fila de encabezado se descarta por el filtro de sensor. Se revisa con el inventario real del nivel (la entrega del 2026-11-01 aún no está en `DATA_DIR`) |
| `evidence_for` lee el nivel también en reportes de lluvia | Se mantiene | Inocuo: la compuerta está en `compute_confidence` (tests de propiedades) |
| Celdas de fecha con zona horaria de otra zona | Se mantiene | openpyxl devuelve fechas sin zona; la hora escrita es local |

## Salida (rutas absolutas de la copia reemplazadas por rutas del repo; sin las líneas de arranque del CLI)

Revisión en solo lectura terminada. No edité nada. No hay git en esta copia, así que verifiqué el estado actual de los archivos contra los documentos. No pude comprobar historial de commits, suite en verde, cobertura, linters ni gitleaks.

## Veredicto

Lo revisado cumple lo esencial de TASK-038, TASK-039, ADR-002 §4 y ADR-004 §8. Encontré solo observaciones menores. Ningún error funcional.

## Subida máxima en 24 h

El algoritmo es correcto. Ventana deslizante con mínimo monótono, calculada globalmente antes de agrupar por día. La medianoche funciona: una lectura del 1-ene mira al mínimo del 31-dic, y el mínimo del día no mira atrás. Hay test que lo fija.

- Borde exacto de 24 h 00: el código conserva el mínimo de hace exactamente 24 h (`<`, no `<=`). Intervalo cerrado, lectura defendible. Pero ningún test lo fija; solo hay test de 24 h 15 m. Sugiero fijarlo con un test.
- Marcas repetidas: se queda la primera en orden de entrada y luego ordena. Hay test.
- Zona horaria de celdas de fecha: `replace(tzinfo=tz)` es correcto porque openpyxl devuelve naive y la hora escrita es local. Solo fallaría ante un datetime aware de otra zona, caso que hoy no ocurre.
- Hojas 2+ del xlsx: `_rows` valida el encabezado solo en la primera hoja y entrega la fila 1 de las demás como dato. Hoy es benigno porque el filtro de sensor la descarta, pero es frágil si otra hoja trae otro orden de columnas.
- Filas cortas (menos de 4 columnas) se omiten en silencio. El lector de estaciones, en cambio, las reporta como error. Una exportación truncada pasaría callada.

## La confianza y el nivel

Correcto en los dos sentidos que pediste:

- Reporte que no afirma creciente, o día sin nivel: la fuente no aparece y el puntaje queda idéntico. Está en `_level_source` y probado con dos tests de propiedades en [test_confidence.py](tests/verification/test_confidence.py).
- `evidence_for` siempre lee el nivel del día, incluso para reportes de lluvia. Es inocuo porque la compuerta está en `compute_confidence`, no en la evidencia.

Una nota de robustez: `_level_rise` toma el máximo entre todas las series del día sin filtrar `EST-A`. Hoy el archivo trae una sola serie, así que no cambia nada. Si algún día trae dos, elegiría la subida mayor e inflaría acuerdos. Filtrar por serie lo blinda.

## El nivel no entra al modelo

Confirmado. Nada en `forecast/` importa `level`. Coherente con ADR-004 §8, `docs/data-model.md` y `docs/data-sources.md`: solo evidencia de crecientes. `climapp-level` quedó registrado en `pyproject.toml`.

## Contrato

Sin discrepancias. `river_level` está en los tres lados: `SourceKind` en [confidence.py](src/climapp/verification/confidence.py:26), enum `kind` en [openapi.yaml](docs/openapi.yaml:229) y tabla Confidence en [data-model.md](docs/data-model.md:113). Campos requeridos y `independent_sources` coinciden. Los tests de contrato validan `Report` y `ReportSummary` contra el yaml.

Cubre además el "hecho cuando" del backlog: tests del lector, medianoche, mínimo expirado, repetidas y las dos propiedades de TASK-039 existen.

## Nombres de estaciones

Limpio. Solo identificadores `EST-x` en código, tests y docs. `LEVEL_EXPORTS` en `.env.example` usa ruta descriptiva y el nombre real queda en `.env`, como exige el ADR. Detalle menor: el test usa `RAW = "ESTACION SINTETICA"` en vez de la convención `raw-a` del repo. No filtra nada real, pero rompe la convención que pidió la revisión del día 1.

## Configuración

`CONFIDENCE_WEIGHT_LEVEL` y `LEVEL_RISE_THRESHOLD_M` están en `Settings`, en `.env.example` con marca SUPUESTO y en `ConfidenceWeights.from_settings`. El test que cruza claves de `.env.example` contra campos impide que se desincronicen.

