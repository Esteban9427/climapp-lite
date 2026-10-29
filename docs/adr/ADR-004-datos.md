# ADR-004: Datos, convención de día, limpieza, imputación, procedencia y licencias

- **Estado:** Aceptado con SUPUESTOS
- **Fecha:** 2026-10-29
- **Relacionados:** ADR-001, `docs/data-sources.md`, R11, R12
- **Revisado:** 2026-10-29 (Early como serie principal)

## Contexto
Inventario de solo lectura del 2026-10-29 [INV]:

| Serie | Tipo | Periodo | Días válidos | Días ≥20 mm |
|-------|------|---------|--------------|-------------|
| EST-A | Estación pluviométrica de la cuenca | 2013-09-29 → 2026-10-22 | 4 566 | 9,6 % |
| EST-B | Estación pluviométrica de la cuenca | 2013-09-29 → 2026-07-07 | 4 467 | 12,8 % |
| EST-C | Estación pluviométrica de la cuenca | 2022-12-30 → 2026-10-22 | 971 | 13,2 % |
| EST-D | Estación pluviométrica de la cuenca | 2023-06-04 → 2025-03-15 | 537 | 6,3 % |
| IMERG Early V07 diario (`GPM_3IMERGDE`) | Satélite, 1 celda de 0,1° · **serie principal** | Por descargar: 2000 → hoy (TASK-009) | — | — |
| IMERG Final diario (`GPM_3IMERGDF`) | Satélite, 1 celda de 0,1° · **solo contraste** | 2000-01-01 → 2025-01-01 (falta 2022-12-31) | — | — |
| CHIRPS diario | Satélite + estaciones, 3 celdas | 1981-01-01 → 2026-09-30 | — | — |

- Las estaciones están en la parte media y la parte alta de la cuenca; la asignación de cada EST a su zona está pendiente de los metadatos. Los nombres reales y la ubicación de las estaciones **no se publican** mientras no haya autorización (D-03). Se usan los identificadores EST-A a EST-D. La correspondencia vive fuera de este repositorio.
- Las estaciones registran un contador acumulado `P` cada 10 min, con reinicios y picos.
- Hay dos exportaciones con datos idénticos en las 3 estaciones comunes (100 % de días iguales); una de ellas agrega EST-B. Una tercera exportación en hoja de cálculo está truncada (1 048 576 filas) y tiene decimales mal parseados: **no se usa**.
- Correlación diaria entre estaciones: entre 0,49 y 0,88. No hay duplicados (ningún par con r ≥ 0,99 ni series idénticas).
- El CSV satelital trae 3 puntos que caen en **la misma celda de 0,1°** con valores idénticos: cuenta como **una sola serie**.
- No se pudo determinar la versión de CHIRPS (pendiente). El IMERG histórico disponible es la **Final Run** según la consulta de descarga original; la versión no está documentada (presumiblemente V07, la vigente; pendiente). Por eso el modelo se entrena con **Early**, que se descarga durante el evento (ADR-001 §3).

## Decisión
1. **Convención de día:** día calendario local (America/Bogota, UTC−05:00) para estaciones y satélite.
   - IMERG diario y CHIRPS agregan por día UTC, que en hora local va de 19:00 a 19:00. En v1 se documenta ese desfase de 5 h y se usa así (SUPUESTO). Si el tiempo alcanza, el día local se reconstruye desde IMERG cada media hora (`Should`).
   - La ventana de 7 a 7 se documenta como **variante**: en el análisis previo bajó la correlación de 0,47 a 0,35.
2. **Limpieza de estaciones** (función pura, con tests):
   - Incremento = diferencia entre lecturas consecutivas del contador.
   - Se ignoran los **descensos** (reinicios) y los **aumentos > 40 mm en 10 min** (picos). Umbral: SUPUESTO.
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

## Consecuencias
- Los nombres de estaciones nunca llegan a git. Un grep en el CI lo vigila (DoD).
- El desfase UTC/local añade ruido al satélite; se mide en lugar de ocultarlo.
- Sin autorización, el plan B pierde la verdad de terreno local, y el pitch lo dice.
