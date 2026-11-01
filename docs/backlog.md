# Backlog — ClimApp Lite

> MoSCoW. Ninguna tarea dura más de 4 h. Las estimaciones suponen trabajo asistido por Claude Code. Responsables: **JE** (desarrollo) y **JM** (validación científica). Cada tarea se hace con TDD y se cierra con commit y una línea en el README (DoD).
> Regla de velocidad: si el viernes la velocidad real supera la estimada, se suben tareas Should al sprint en el orden de la tabla de abajo. Nunca al revés.

## Capacidad del Sprint 1 (2026-10-30 → 2026-11-02)
| Persona | vie 30 | sáb 31 | dom 1 | lun 2 (festivo) | Total | Foco declarado (85 %) | Límite FORGE G3 (80 %) |
|---------|--------|--------|-------|-----------------|-------|-----------------------|------------------------|
| JE | 6 h (trabaja en su empleo) | 12 h | 12 h | 10 h | **40 h** | 34 h | **32 h** |
| JM | — | — | — | — | **8 h** (declaradas por JM el 2026-10-29; por confirmar, PRD SP-11) | 6,8 h | **6,4 h** |

JE compromete **32 h** (el valor menor de los dos, así que se cumplen la regla de foco y la de G3). JM compromete **8 h** (TASK-020, TASK-002 y TASK-021): el **100 % de su capacidad**, por encima del 80 % de G3. Es una **excepción aprobada por el equipo el 2026-10-29**; JM declaró 8 h el 2026-10-29, pendientes de confirmar, y si son menos, TASK-021 vuelve a la cola de Should. El congelamiento (`SCOPE_FREEZE_DATE=2026-11-02`) se aplica **al cierre** del lunes 2-nov.

## Línea de corte (aprobada el 2026-10-29)
Todos los Must suman **37,5 h para JE**: no caben en 32 h. Ni siquiera cabían aplicando el orden de sacrificio acordado (sensibilidades → contraste Early↔Final → pulido del mapa), porque esas tres tareas ya eran Should. Sin tocar los innegociables (aviso de no alerta oficial, compuerta de verificación, explicación con Muse Spark y reproducción de la demo), se aplicaron además estos recortes:

| # | Baja a Should | Ahorro | Efecto |
|---|---------------|--------|--------|
| 4 | TASK-029 Evaluación sin EST-B | 1 h | El modelo sigue siendo robusto a la pérdida de EST-B por diseño (agregados con las estaciones disponibles); lo que se pierde es el informe comparativo |
| 5 | TASK-009 + TASK-028 IMERG Early 2000→hoy | 4 h | El sprint arranca con el **plan B de Earthdata** (estaciones + CHIRPS; IMERG solo como evidencia). Early es el **primer** Should en entrar si el viernes va por delante |
| — | TASK-001 se reestima de 1,5 a 1 h | 0,5 h | Con Claude Code, el esqueleto es configuración |

JE compromete **32 h**; JM, **8 h**. El sprint arranca en `DATA_PLAN=plan_b_earthdata`.

| Orden de entrada si sobra capacidad | Tarea | Horas |
|-------------------------------------|-------|-------|
| 1 | TASK-009 Descarga de IMERG Early 2000→hoy (JE; vuelve de JM el 2026-10-30) | 3 |
| 2 | TASK-028 Early a la tabla diaria y al modelo (JE; entra cuando TASK-009 esté lista y haya holgura) | 1 |
| 3 | TASK-029 Evaluación con y sin EST-B | 1 |
| 4 | TASK-030 Pulido del mapa | 2 |
| 5 | TASK-033 Contraste Early↔Final | 2 |
| 6 | TASK-031 Sensibilidad del umbral (10 y 50 mm) | 2 |
| 7 | TASK-032 Sensibilidad de la regla de objetivo | 1 |
| 8 | TASK-034 Comparación con estaciones individuales | 1,5 |
| 9 | TASK-037 Intensidad horaria observada | 1,5 |
| — | TASK-021 Set de evaluación de reportes (**comprometida para JM** dentro de sus 8 h) | 3 |

## Plan por día (JE, comprometido)
| Día | Tareas | Horas | Salida verificable |
|-----|--------|-------|--------------------|
| vie 30 | TASK-001, 003, 005 | 4,5 | Lectura limpia con tests en verde |
| sáb 31 | TASK-004, 006, 007, 008, 015 | 10 | Tabla diaria, RF y `GET /evaluation` |
| dom 1 | TASK-011, 012, 013, 014, 022 | 9,5 | Compuerta y explicación con tests |
| lun 2 | TASK-016, 017, 018, 019 | 8 | Web móvil con aviso y demo reproducible; **congelamiento al cierre** |
| **Total** | | **32** | |

JM: TASK-020 (vie 30, 12:00), TASK-002 (sáb 31, después de TASK-004) y TASK-021 (desde el dom 1, cuando TASK-012 esté lista) = 8 h.

Dentro de cada día, **el orden es el de la lista** (hay dependencias intradía: 012 → 013 → 014 y 013 → 022 el domingo; 016 → 017 → 018 y 017 → 019 el lunes). **dom 1:** decisión de D-03 (plan B de datos, TASK-035).

---

## Must comprometidas
### TASK-001 — Esqueleto del proyecto
- **Estimación:** 1 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** —
- `pyproject.toml` con uv, pytest, pytest-cov, ruff, mypy strict, structlog y pydantic-settings; `src/climapp/` según CLAUDE.md; `Settings` que lee las claves de `.env.example`.
- **Hecho cuando:** `uv run pytest` corre un test de `Settings` en verde y `ruff` y `mypy` pasan.

### TASK-002 — Inventario de estaciones
- **Estimación:** 3 h · **MoSCoW:** Must · **Responsable:** JM · **Depende de:** TASK-004
- Comando que reporta, por estación, el periodo, los días válidos, la correlación por pares y los posibles duplicados (r ≥ 0,99 o días idénticos), con salida en `DATA_DIR/derived/inventory.json`; también calcula los grupos con r ≥ `STATION_GROUP_MIN_R` (0,8 por defecto, SUPUESTO; ADR-002).
- Orden del sábado: JE cierra TASK-004 por la mañana; JM empieza TASK-002 al terminar.
- **Hecho cuando:** tests con fixtures sintéticos detectan un duplicado plantado, y el informe real coincide con ADR-004.

### TASK-003 — Lectura del contador y limpieza
- **Estimación:** 2,5 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-001
- Lector de las dos exportaciones (xls, y csv con coma decimal ambigua) y cálculo de incrementos, ignorando descensos y aumentos > 40 mm en 10 min.
- **Hecho cuando:** hay tests de reinicio, pico, coma decimal y valor vacío.

### TASK-004 — Tabla diaria de estaciones
- **Estimación:** 2,5 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-003
- `DailyPrecip` por día local, con `valid` (≥ 100/144), `imputed=false` y `source_hash`; une las dos exportaciones sin duplicar.
- **Hecho cuando:** los tests cubren el borde de 99/100 lecturas, el cambio de día local y la unión de exportaciones idénticas.

### TASK-005 — Lector de CHIRPS
- **Estimación:** 1 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-001
- Hojas de cálculo de CHIRPS: descarta las filas MIN, PROM y MAX y las columnas sin celda.
- **Hecho cuando:** los tests verifican el descarte de las filas resumen.

### TASK-006 — Objetivo de cuenca (regla principal)
- **Estimación:** 1 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-004
- `TARGET_RULE=basin_mean` (SUPUESTO hasta JM) sobre las estaciones válidas de cada día.
- **Hecho cuando:** hay tests sintéticos con días de 1, 2 y 4 estaciones disponibles, y aparte, el comando sobre los datos reales reproduce la frecuencia de ADR-001 (10,2 %; verificación manual, no test unitario).

### TASK-007 — Líneas base y métricas
- **Estimación:** 2,5 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-006
- Climatología (día del año ±15) y persistencia; POD, FAR, CSI, Brier, AUC y calibración; exclusión de días imputados.
- **Hecho cuando:** hay tests con casos calculados a mano y un test de que lo imputado no entra.

### TASK-008 — Variables y random forest
- **Estimación:** 3 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-005, TASK-007
- Agregados de la cuenca (media, máximo y dispersión en t, t-1 y t-2) **con las estaciones disponibles cada día** y el número de estaciones como variable; acumulado de 3 días; satélite según `data_plan`; estacionalidad; partición temporal; calibración isotónica.
- **Hecho cuando:** un test de fuga verifica que ninguna fecha de prueba aparece en entrenamiento, un test verifica que los agregados ignoran las estaciones sin dato, y las métricas quedan en `DATA_DIR/derived/evaluation.json`.

### TASK-011 — Cliente Muse y fallback
- **Estimación:** 1,5 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-001
- SDK `openai` con `base_url`, modelo y esfuerzo desde `Settings`; respuestas grabadas con `DEMO_FALLBACK=1`.
- **Hecho cuando:** los tests con un cliente falso cubren los parámetros enviados (`reasoning_effort` por tarea y `max_tokens = MUSE_MAX_TOKENS`, que vale 2000; la configuración rechaza valores < 2000) y el fallback.

### TASK-012 — Comprobaciones deterministas
- **Estimación:** 2,5 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-011
- En el orden de ADR-002 §3: `finish_reason == "stop"` → contenido no vacío → esquema → cifras iguales → herramientas permitidas. Se reportan todos los motivos que fallen, en ese orden.
- **Hecho cuando:** hay un test por motivo de rechazo y uno del orden de los motivos.

### TASK-013 — Juez y bucle de 3 intentos
- **Estimación:** 2,5 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-012
- Juez con `reasoning_effort=medium`; reintentos con los motivos anteriores; `requiere_revision_humana` tras el tercer fallo.
- **Hecho cuando:** los tests cubren aprobación al primer intento, al tercero y el paso a revisión humana.

### TASK-014 — Confianza por código
- **Estimación:** 1,5 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-002, TASK-012
- Grupos de estaciones (de TASK-002) que cuentan como una fuente; puntaje con desglose; pesos fijos SUPUESTO desde la configuración (la calibración es Should, TASK-021).
- **Hecho cuando:** un test de propiedades verifica que duplicar una estación correlacionada no sube la confianza, y la función es pura.

### TASK-015 — API de pronóstico y evaluación
- **Estimación:** 1 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-008
- `GET /forecast` y `GET /evaluation` según `openapi.yaml`, sobre artefactos precalculados, con `data_plan`.
- **Hecho cuando:** hay tests de contrato contra el esquema OpenAPI, de los casos 503 y `stale`, y de que el aviso siempre está presente.

### TASK-016 — API de reportes
- **Estimación:** 2 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-013, TASK-014
- `POST /reports` (202 asíncrono, EXIF eliminado, polígono de la cuenca), `GET /reports` y `GET /reports/{id}`.
- **Hecho cuando:** hay tests de contrato, fuera de cuenca, foto > 5 MB y EXIF eliminado.

### TASK-017 — Vista de pronóstico, formulario y lista de reportes
- **Estimación:** 3 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-015, TASK-016, TASK-022
- Jinja2 + HTMX, mobile-first; aviso "no es alerta oficial" con enlace; explicación verificada; formulario con sondeo de estado; lista simple de reportes verificados.
- **Hecho cuando:** hay tests HTTP del HTML (aviso presente, explicación nula y estados) y una revisión manual en 360 px.

### TASK-018 — Mapa mínimo (marcadores)
- **Estimación:** 1 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-017
- Leaflet con OSM (atribución ODbL), un marcador por reporte verificado y el resultado del día en la leyenda.
- **Hecho cuando:** un test verifica que el HTML incluye la atribución y los marcadores del día.

### TASK-019 — Reproducción histórica para la demo
- **Estimación:** 2 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-017, TASK-020 (evento elegido)
- `replay_date` de punta a punta con `DEMO_FALLBACK=1`, con el indicador "reproducción histórica".
- **Hecho cuando:** la demo corre sin red, con un test end-to-end.

### TASK-020 — Validación de SUPUESTOS
- **Estimación:** 2 h · **MoSCoW:** Must · **Responsable:** JM · **Depende de:** — (2026-10-30, 12:00)
- Confirmar o corregir SP-1 a SP-8 (PRD), la regla principal del objetivo, el umbral de agrupación, el evento de la demo y las 8 h de capacidad de JM.
- **Avance (2026-10-30):** JM respondió el 2026-10-29. Resueltos: umbral de 20 mm con fuente (pendiente de segunda revisión), categorías horarias del IDEAM (URL pendiente), orden altitudinal, eventos candidatos (año de E2 confirmado por la prensa; evento recomendado en el PRD) y reasignación de TASK-009. Siguen SUPUESTO: regla de cuenca (SP-6) y umbral de agrupación (SP-7). Nuevas preguntas para JM: SP-12 y SP-13.
- **Si JM no responde antes del 30-oct a las 18:00:** los SUPUESTOS siguen vigentes tal cual y JE elige el evento de la demo: el día con mayor media de la cuenca en el periodo apartado que tenga datos de al menos 2 estaciones. Queda anotado como SUPUESTO.
- **Hecho cuando:** el PRD y los ADR están actualizados, sin SUPUESTOS resueltos que sigan marcados.

### TASK-022 — Explicación verificada del pronóstico
- **Estimación:** 1,5 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-013
- Muse Spark explica el pronóstico; la compuerta exige que las cifras coincidan.
- **Hecho cuando:** un test verifica que una cifra alterada se rechaza y que `explanation=null` si no pasa.

## Contingente (D-03)
### TASK-035 — Plan B de datos sin estaciones
- **Estimación:** 1,5 h · **MoSCoW:** Must **solo si** D-03 no está cerrado el 2026-11-01 (contingencia **aprobada** el 2026-10-29) · **Responsable:** JE · **Depende de:** TASK-005, TASK-008
- `DATA_PLAN=plan_b_datos`: objetivo y variables sobre CHIRPS e IMERG Early, sin estaciones; la demo se reproduce sobre CHIRPS.
- Si se activa, consume 1,5 h de las 2 h que hay entre el límite de G3 (32 h) y el foco declarado (34 h). El equipo aprobó el 2026-10-29 pasar del 80 % en ese caso.
- **Hecho cuando:** un test verifica que con `plan_b_datos` ninguna serie `EST-*` entra al modelo.

## Should (en orden de entrada)
### TASK-009 — Descarga de IMERG Early V07 2000→hoy
- **Estimación:** 3 h · **MoSCoW:** Should (primera en entrar) · **Responsable:** JE · **Depende de:** TASK-001
- Código nuevo dentro del repo (`src/climapp/data/imerg_early.py`), con test. **Prohibido reutilizar o adaptar código de los notebooks previos al evento.**
- Descarga con Earthdata (`EARTHDATA_TOKEN`) de `GPM_3IMERGDE` para la celda de la cuenca, con caché en `DATA_DIR/raw/imerg_early/`, hash y reintentos. Mide la latencia real de los últimos días (SP-9).
- **Hecho cuando:** un test con un servidor falso cubre el reintento y la caché, y la serie real queda completa o con los faltantes listados.
- Primer paso (15 min, incluido): estimar el volumen y la velocidad de descarga. Si el total supera 4 h, la tarea se parte **antes de empezar** en TASK-009a (2000-2012) y TASK-009b (2013→hoy). La descarga desatendida corre en segundo plano y no cuenta como horas de JE.

### TASK-028 — IMERG Early a la tabla diaria y al modelo
- **Estimación:** 1 h · **MoSCoW:** Should · **Responsable:** JE · **Depende de:** TASK-009, TASK-008
- Serie `IMERG_E` en `DailyPrecip`; `data_plan=principal`; se reentrena y reevalúa.
- **Hecho cuando:** un test verifica que el modelo usa `IMERG_E` y nunca `IMERG_F`.

### TASK-029 — Evaluación con y sin EST-B
- **Estimación:** 1 h · **MoSCoW:** Should · **Responsable:** JE · **Depende de:** TASK-008
- `scenarios.sin_est_b` en la evaluación, tratando EST-B como no disponible en todo el periodo de prueba.
- **Hecho cuando:** un test verifica que, en el escenario sin EST-B, ningún agregado usa sus datos.

### TASK-030 — Pulido del mapa
- **Estimación:** 2 h · **MoSCoW:** Should · **Responsable:** JE · **Depende de:** TASK-018
- Colores por resultado diario, ventana emergente con la confianza y selector de fecha.

### TASK-033 — Contraste Early↔Final
- **Estimación:** 2 h · **MoSCoW:** Should · **Responsable:** JE · **Depende de:** TASK-028
- Lector del CSV de IMERG Final (3 puntos → una serie); sesgo y correlación en `imerg_final_vs_early`.

### TASK-031 — Sensibilidad del umbral (10 y 50 mm)
- **Estimación:** 2 h · **MoSCoW:** Should · **Responsable:** JE · **Depende de:** TASK-008

### TASK-032 — Sensibilidad de la regla de objetivo
- **Estimación:** 1 h · **MoSCoW:** Should · **Responsable:** JE · **Depende de:** TASK-006
- Reglas `any_station` y `reference_station` como sensibilidad.

### TASK-034 — Comparación con estaciones individuales
- **Estimación:** 1,5 h · **MoSCoW:** Should · **Responsable:** JE · **Depende de:** TASK-008

### TASK-037 — Intensidad horaria observada
- **Estimación:** 1,5 h · **MoSCoW:** Should · **Responsable:** JE · **Depende de:** TASK-004
- Indicador descriptivo (ADR-001 §12), nunca objetivo del modelo: por estación y día, máximo de la suma móvil de 6 lecturas de 10 min sin huecos, con la categoría horaria del IDEAM (umbrales desde la configuración; fuente en PRD SP-3) y la lectura máxima de 10 min de esa ventana.
- **Hecho cuando:** hay tests sintéticos de los bordes de categoría (2, 15 y 30 mm/h), de una ventana con hueco que no cuenta y de un salto aislado en una lectura que queda visible en la lectura máxima de 10 min; y un test verifica que el indicador no entra como objetivo.

### TASK-038 — Lector de nivel del río y serie diaria
- **Estimación:** 2 h · **MoSCoW:** Should · **Responsable:** JE · **Depende de:** TASK-001
- `climapp-level`: lee la exportación de nivel de EST-A (xlsx cada 15 min) y escribe en `DATA_DIR/derived/` la serie diaria con nivel mínimo, máximo y subida máxima en 24 h (ADR-004 §8).
- **Hecho cuando:** hay tests sintéticos del lector (encabezado, sensor, vacíos, fila mal formada), de la subida a través de la medianoche, del mínimo de más de 24 h que no cuenta y de las marcas repetidas.

### TASK-039 — Subida de nivel como evidencia de crecientes
- **Estimación:** 2 h · **MoSCoW:** Should · **Responsable:** JE · **Depende de:** TASK-014, TASK-038
- Fuente aparte de la lluvia en la confianza, solo para reportes que afirman creciente (ADR-002 §4). Peso y umbral de subida: SUPUESTO para JM, fijados antes de evaluar la demo.
- **Hecho cuando:** tests de propiedades verifican que sin nivel ese día, o en un reporte que no afirma creciente, la confianza no cambia.

### TASK-009b — Cliente IMERG Early NRT (PPS)
- **Estimación:** 3 h · **MoSCoW:** Should · **Responsable:** JE · **Depende de:** TASK-001
- Descarga de IMERG Early casi en tiempo real del servidor NRT de PPS, recortada a la celda o celdas de la cuenca, con caché, reintentos y sin duplicados; mide la latencia real (SP-9). Solo evidencia en la verificación de reportes, no en el modelo.
- **Hecho cuando:** un test con un servidor falso cubre credenciales desde `.env` o `~/.netrc`, el recorte, la caché, el reintento y los duplicados.

### TASK-021 — Set de evaluación de reportes
- **Estimación:** 3 h · **MoSCoW:** Should, **comprometida para JM** dentro de sus 8 h · **Responsable:** JM · **Depende de:** TASK-012
- Al menos 30 reportes sintéticos etiquetados; tasa de aprobación y costo por reporte (NFR-3) en `eval-harness/`.

## Could
### TASK-023 — Día local desde IMERG cada media hora
- **Estimación:** 4 h · **MoSCoW:** Could · **Responsable:** JE · **Depende de:** TASK-009

### TASK-024 — Containerfile con Podman
- **Estimación:** 2 h · **MoSCoW:** Could · **Responsable:** JE · **Depende de:** TASK-017

## Después del congelamiento (2026-11-03 → 2026-11-04)
### TASK-025 — QA hacia el gate 4
- **Estimación:** 4 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** todas las Must comprometidas (TASK-001 a TASK-022 de la línea de corte)
- Cobertura (≥ 85 % en el núcleo, ≥ 70 % global), SAST, gitleaks y 0 bugs CRITICAL/HIGH.

### TASK-026 — Video de demo de 3 min
- **Estimación:** 3 h · **MoSCoW:** Must · **Responsable:** JE + JM · **Depende de:** TASK-019
- Solo funciones construidas en el evento (R10).

### TASK-027 — Entrega
- **Estimación:** 1 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-025, TASK-026
- Enviar antes de las 18:00 hora Cali del 2026-11-04 (límite: 21:00).

## Won't (v1)
Sequía e incendios · audio · cuentas · notificaciones · app nativa · plataforma histórica · investigadores · reentrenamiento automático.

## Cambios
- 2026-10-29: IMERG Early pasa a ser la serie principal. La antigua tarea de "variante operativa" (el ID 010) se elimina porque el modelo principal ya es operativo; **el ID 010 no se reutiliza**. Se agregan TASK-028 a TASK-035. Capacidad real y línea de corte propuesta.
- 2026-10-29: se atiende la revisión de Muse Code (`docs/reviews/spec-gate.md`).
- 2026-10-29: **el equipo aprueba la línea de corte.** TASK-029, TASK-009 y TASK-028 pasan a Should y el sprint arranca en `plan_b_earthdata`. TASK-009 se asigna a JM (5 + 3 = 8 h, SUPUESTO hasta su confirmación del 30-oct a las 12:00; excepción al 80 % de G3). TASK-028 (JE) entra cuando TASK-009 esté lista y haya holgura. TASK-035 queda aprobada como contingencia si D-03 no está cerrado el 2026-11-01, usando la holgura entre 32 y 34 h.
- 2026-10-30 (fuente: respuestas de JM del 2026-10-29, TASK-020): TASK-009 vuelve a JE como Should (primera en entrar); JM queda en TASK-020, TASK-002 y TASK-021 (8 h, por confirmar). Se crea **TASK-037** (intensidad horaria observada, Should, JE, 1,5 h). Umbral de 20 mm con fuente (pendiente de segunda revisión), categorías horarias del IDEAM separadas del umbral diario, orden altitudinal de las estaciones y evento de la demo recomendado (PRD SP-5).
- 2026-10-30: **el equipo aprueba E1 (2025-01-01) como evento de la demo** (PRD SP-5 cerrado; TASK-019 ya no depende de esa decisión).
- 2026-10-30 (TASK-003): la marca `suspect` de SP-12 entra dentro de la estimación de TASK-003 (no se crea tarea Should). Con la regla literal (1 h sin lluvia) no se marca el salto que motivó SP-12, porque la hora posterior tiene 1,8 mm; se agrega `SUSPECT_QUIET_MAX_MM` (0 por defecto) para que la decisión de JM sea solo de configuración (PRD SP-12).
- 2026-10-30 (TASK-004, adelantada del sábado): la tabla diaria reproduce la tabla de E1 del PRD y los días válidos de EST-C y EST-D del inventario; EST-A y EST-B suman 12 días válidos más porque la tabla empieza el 2013-09-16 y el inventario el 2013-09-29 (a revisar en TASK-002). Se agrega `n_suspect` a `DailyPrecip` (`docs/data-model.md`).
- 2026-10-30: **corrección de huecos del contador** (Must, antes de TASK-006, fuera de las tareas numeradas). El equipo eligió anular solo los pasos > `MAX_GAP_MIN` que cruzan el día local; los del mismo día conservan la lluvia (ADR-004 §2, PRD SP-14). Se agrega `n_gap` a `DailyPrecip`.
- 2026-10-30 (TASK-008): decisiones del equipo tras ver la primera evaluación (ADR-001 §1, §3, §5 y §9): calibración isotónica fuera de muestra 2020-2022 (único cambio mirando la prueba, registrado como tal) y dos variantes por disponibilidad de datos: `operativa` (en vivo) e `historica` (con CHIRPS, solo reproducción). Riesgo nuevo PRD R16. Contrato: `variant` en `GET /forecast` y en `Forecast`.
- 2026-10-31: **TASK-002 pasa a JE**, porque JM dedica sus 8 h a los eventos y a los ~30 reportes de ejemplo (TASK-021). Solo se implementa lo que necesita TASK-014: grupos de estaciones con r ≥ `STATION_GROUP_MIN_R` sobre la tabla diaria (`climapp-groups`, `STATION_GROUPS_FILE`). El inventario completo (periodos, días válidos, duplicados e `inventory.json`) queda fuera del sprint. Por decisión del equipo, los grupos se calculan con toda la tabla y no solo con el entrenamiento (ADR-002 §4): [EST-A], [EST-B, EST-C] (r = 0,874) y [EST-D]. Los 12 días válidos extra de EST-A y EST-B frente al inventario (Cambios, 2026-10-30) siguen sin revisar.
- 2026-11-01 (fuente: entrega de JM del 2026-11-01 y pedido de JE): se agregan TASK-038 (lector de nivel), TASK-039 (subida de nivel como evidencia de crecientes) y TASK-009b (cliente IMERG Early NRT), las tres Should de JE. El nivel nunca entra al modelo.
