# ADR-004: Datos, convención de día, limpieza, imputación, procedencia y licencias

- **Estado:** Aceptado con SUPUESTOS
- **Fecha:** 2026-10-29
- **Relacionados:** ADR-001, `docs/data-sources.md`, R11, R12
- **Revisado:** 2026-10-29 (Early como serie principal) · 2026-10-30 (orden altitudinal por posición; hallazgos de calidad de TASK-020; huecos del contador)

## Contexto
Inventario de solo lectura del 2026-10-29 [INV]:

| Serie | Tipo | Periodo | Días válidos | Días ≥20 mm |
|-------|------|---------|--------------|-------------|
| EST-A | Estación pluviométrica de la cuenca · posición media | 2013-09-29 → 2026-10-22 | 4 566 | 9,6 % |
| EST-B | Estación pluviométrica de la cuenca · posición media-alta | 2013-09-29 → 2026-07-07 | 4 467 | 12,8 % |
| EST-C | Estación pluviométrica de la cuenca · posición alta | 2022-12-30 → 2026-10-22 | 971 | 13,2 % |
| EST-D | Estación pluviométrica de la cuenca · posición piedemonte | 2023-06-04 → 2025-03-15 | 537 | 6,3 % |
| IMERG Early V07 diario (`GPM_3IMERGDE`) | Satélite, 1 celda de 0,1° · **serie principal** | Por descargar: 2000 → hoy (TASK-009) | — | — |
| IMERG Final diario (`GPM_3IMERGDF`) | Satélite, 1 celda de 0,1° · **solo contraste** | 2000-01-01 → 2025-01-01 (falta 2022-12-31) | — | — |
| CHIRPS diario | Satélite + estaciones, 3 celdas | 1981-01-01 → 2026-09-30 | — | — |

- **Orden altitudinal, de arriba abajo** [JM, 2026-10-29]: EST-C (alta) → EST-B (media-alta) → EST-A (media) → EST-D (piedemonte, donde el río pierde pendiente). En este repositorio solo se publica la **posición**, nunca la altitud ni las coordenadas. Las tablas y vistas ordenan las estaciones en ese orden. Los nombres reales y la ubicación de las estaciones **no se publican** mientras no haya autorización (D-03). Se usan los identificadores EST-A a EST-D. La correspondencia vive fuera de este repositorio.
- Las estaciones registran un contador acumulado `P` cada 10 min, con reinicios y picos.
- Hay dos exportaciones con datos idénticos en las 3 estaciones comunes (100 % de días iguales); una de ellas agrega EST-B. Una tercera exportación en hoja de cálculo está truncada (1 048 576 filas) y tiene decimales mal parseados: **no se usa**.
- Correlación diaria entre estaciones: entre 0,49 y 0,88. No hay duplicados (ningún par con r ≥ 0,99 ni series idénticas).
- Hallazgos de calidad del análisis de eventos (TASK-020, 2026-10-30; resueltos con JM el 2026-10-30, ver PRD SP-12 y SP-13 y §2):
  - EST-A, 2024-12-31 23:50: un salto aislado de 38,6 mm en una sola lectura de 10 min, sin lluvia en la hora anterior ni en la posterior. Pasa el filtro de > 40 mm y fabrica un día de 52,6 mm.
  - EST-B, 2022-01-01 → 2022-03-01: el contador sube ≈ 6 mm en dos meses con días completos de lecturas (luego se pone en 0 el 2022-03-01 a las 14:00), mientras EST-A registra días de 40-52 mm. El criterio de ≥ 100/144 lecturas no lo detecta. JM confirma una falla del balancín.
- El CSV satelital trae 3 puntos que caen en **la misma celda de 0,1°** con valores idénticos: cuenta como **una sola serie**.
- No se pudo determinar la versión de CHIRPS (pendiente). El IMERG histórico disponible es la **Final Run** según la consulta de descarga original; la versión no está documentada (presumiblemente V07, la vigente; pendiente). Por eso el modelo se entrena con **Early**, que se descarga durante el evento (ADR-001 §3).

## Decisión
1. **Convención de día:** día calendario local (America/Bogota, UTC−05:00) para estaciones y satélite.
   - IMERG diario y CHIRPS agregan por día UTC, que en hora local va de 19:00 a 19:00. En v1 se documenta ese desfase de 5 h y se usa así (SUPUESTO). Si el tiempo alcanza, el día local se reconstruye desde IMERG cada media hora (`Should`).
   - La ventana de 7 a 7 se documenta como **variante**: en el análisis previo bajó la correlación de 0,47 a 0,35.
2. **Limpieza de estaciones** (función pura, con tests):
   - Incremento = diferencia entre lecturas consecutivas del contador.
   - Se ignoran los **descensos** (reinicios) y los **aumentos > 40 mm en 10 min** (picos). Umbral: SUPUESTO.
   - **Huecos** (decisión del equipo, 2026-10-30): un paso entre lecturas separadas por más de `MAX_GAP_MIN` (20 min, SUPUESTO) que **cruza el límite del día local** no se atribuye como lluvia (`GAP`, 0 mm), porque no se sabe en qué día cayó ni si hubo un reinicio en medio. Si el paso queda **dentro del mismo día**, el contador acumulado sí atribuye bien la lluvia: se conserva y se marca `GAP_INTRADAY`. Ambos se cuentan en `n_gap` de la tabla diaria. Se descartó anular todo paso > 20 min: EST-C tiene 342 huecos de 20 min a 6 h dentro del día (cortes de transmisión durante tormentas) con 1 611 mm, y perdía 39 de sus días ≥ 20 mm. Con la regla adoptada cambian 9, 7, 21 y 38 días (EST-A, B, C y D) y dejan de ser ≥ 20 mm 0, 1, 5 y 2. Confirmado por JM [JM 2026-10-30]: los cortes de EST-C fueron fallas de transmisión por la dirección de la antena durante un año, con el contador sumando (PRD SP-14).
   - **Saltos aislados** [JM 2026-10-30, PRD SP-12]: un aumento ≥ `SUSPECT_STEP_MM` (30 mm, SUPUESTO) que cierra un hueco > `MAX_GAP_MIN` dentro del día es lluvia acumulada durante el corte (`GAP_INTRADAY`, se conserva). Si lo preceden lecturas regulares (sin `GAP` ni `GAP_INTRADAY` en los `SUSPECT_QUIET_MIN` = 60 min previos) con el contador quieto, y lo sigue la misma calma, es `suspect`: cada ventana tolera hasta `SUSPECT_QUIET_MAX_MM` = 2 mm [JM 2026-10-30]. Su lluvia **no se suma** a `precip_mm`: queda en `n_suspect` y `suspect_mm` para auditoría.
   - **Periodos de falla conocidos** [JM 2026-10-30, PRD SP-13]: los que el criterio de lecturas no detecta (sensor que transmite pero no registra) se declaran en el archivo versionado `KNOWN_OUTAGES_FILE` (`config/known_outages.json`: `series_id`, `desde`, `hasta`, `motivo`, `fuente`; solo identificadores `EST-x`). Sus días, con ambos extremos incluidos, quedan `valid=false` y sin `precip_mm`. Primer registro: EST-B, del 2022-01-01 al 2022-03-01, falla del balancín.
   - Día válido: **≥ 100 de 144 lecturas**; si no, vacío (SUPUESTO). [OMM] pág. PDF 18 e [IDEAM] pág. 3 solo dan criterios mensuales (11 días o 5 consecutivos faltantes; 80 % del mes).
   - Día con lluvia: ≥ 1 mm ([OMM] pág. PDF 14).
   - En el CHIRPS de hoja de cálculo se descartan las filas resumen (MIN, PROM y MAX) y las columnas sin encabezado de celda.
3. **Imputación:** las series cortas solo se rellenan con estaciones vecinas si quedan marcadas `imputado=true`. **Los días imputados nunca entran en la evaluación** (ni en el objetivo ni en las métricas). Hay un test que lo garantiza.
4. **Procedencia:**
   - Los datos crudos viven en `DATA_DIR` (fuera de git), con hashes SHA-256 en `DATA_DIR/SHA256SUMS`.
   - La tabla diaria derivada se regenera con un comando reproducible. Las tablas de análisis previas solo sirven para contrastar.
   - Los notebooks previos al evento solo se leyeron para extraer metadatos: no se copia ni se adapta su código.
5. **Licencias y autorizaciones:** ver `docs/data-sources.md`.
   - IMERG: datos libres con atribución.
   - CHIRPS: dominio público.
   - Estaciones: autorización pendiente. Si no llega antes del 2026-11-01, se aplica el **plan B de datos (D-03)**: modelo y demo solo con CHIRPS e IMERG Early, con el objetivo definido sobre CHIRPS (SUPUESTO del plan B).
6. **IMERG Early V07 diario de 2000 a hoy** (`GPM_3IMERGDE`, celda de la cuenca): se descarga con Earthdata (`EARTHDATA_TOKEN`), se guarda en `DATA_DIR/raw/imerg_early/` con su hash y entra a la tabla diaria como `IMERG_E`. Si Earthdata falla, se aplica el **plan B de Earthdata** (ADR-001 §5). El IMERG Final del CSV histórico entra como `IMERG_F`, solo para el contraste Early↔Final [Should].

7. **Polígono de la cuenca (TASK-016, 2026-10-31):** `POST /reports` rechaza como `fuera_de_cuenca` los puntos fuera del GeoJSON de `BASIN_POLYGON_FILE` (`Polygon` o `MultiPolygon`, en `DATA_DIR`, fuera de git). Si falta, `POST /reports` responde 503 `sin_poligono` y el resto de la app sigue funcionando. La entrega del 2026-10-29 no trae el límite de la cuenca. **Provisional en uso (SUPUESTO, aprobado por el equipo el 2026-10-31):** `data/basin.geojson`, un rectángulo de lat 3,266 a 3,369 y lon −76,705 a −76,507. Es la extensión de los 15 tramos `waterway=river` "Río Pance" de OpenStreetMap (ODbL, Overpass API, consultado el 2026-10-31; cauce: lat 3,2861 a 3,3486, lon −76,6847 a −76,5275), más un margen de 0,02°. La fuente, la licencia y la fecha van en las propiedades del GeoJSON. Envuelve el cauce, no es el límite hidrográfico (PRD SP-16). El polígono oficial lo aporta JM.
8. **Nivel del río (TASK-038, 2026-11-01):** la exportación de nivel de la estación de la parte media (EST-A; mismo proveedor que las estaciones, uso autorizado el 2026-10-31) trae `STATION_ID, SENSORNAME, FECHAYHRA, ED_VALUE` en m cada 15 min. `climapp-level` la lee (`LEVEL_EXPORTS`, sensor `LEVEL_SENSOR`), mapea la estación con `STATION_MAP_FILE` y escribe `LEVEL_DAILY_FILE` con, por día local, `n_readings`, `level_min_m`, `level_max_m` y `rise_24h_max_m`: para cada lectura del día, su nivel menos el mínimo de las lecturas de las 24 h anteriores (incluida ella), y el máximo de eso; un nivel que baja da 0. Ante marcas de tiempo repetidas se queda la primera; los días sin lecturas no aparecen. No hay criterio de día válido ni limpieza de valores raros todavía: queda pendiente del inventario del nivel (los archivos de la entrega del 2026-11-01 aún no están en `DATA_DIR`). El nombre real del archivo lleva el nombre de la estación, así que solo vive en `.env`. **El nivel no entra al modelo** (ADR-001 §1): solo es evidencia de crecientes en la confianza (ADR-002 §4, TASK-039).

## Consecuencias
- Los nombres de estaciones nunca llegan a git. Un grep en el CI lo vigila (DoD).
- El desfase UTC/local añade ruido al satélite; se mide en lugar de ocultarlo.
- Sin autorización, el plan B pierde la verdad de terreno local, y el pitch lo dice.
