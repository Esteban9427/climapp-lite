# Backlog — ClimApp Lite

> MoSCoW. Ninguna tarea dura más de 4 h. Responsables: **JE** (desarrollo) y **JM** (validación científica). Cada tarea se hace con TDD y cierra con commit y una línea en el README (DoD).

## Sprint 1: 2026-10-30 → 2026-11-02 (congelamiento el 2026-11-02)
**Capacidad (SUPUESTO, por confirmar):** JE 12 h/día × 4 = 48 h → 80 % = **38,4 h**; JM 4 h/día × 4 = 16 h → 80 % = **12,8 h**.

| Compromiso | JE | JM |
|------------|----|----|
| Comprometido (línea de corte) | TASK-001, 003, 004, 005, 007, 008, 011, 012, 013, 014, 015, 016, 017 = **36 h** | TASK-002, 006, 020, 021 = **10 h** |
| Must sobre la línea de corte (sin capacidad) | TASK-009, 010, 018, 019, 022 = **14 h** | — |

> ⚠️ Los **Must suman 50 h para JE** frente a 38,4 h de capacidad. Para no pasar del 80 %, las cinco tareas Must sobre la línea de corte entran solo si la capacidad real es mayor o si se reasignan. Decisión pendiente del equipo.

Orden del sprint: 30-oct datos → 31-oct modelo y verificación → 1-nov API y web → 2-nov cierre y congelamiento.

---

### TASK-001 — Esqueleto del proyecto
- **Estimación:** 2 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** —
- `pyproject.toml` con uv, pytest, pytest-cov, ruff, mypy strict, structlog y pydantic-settings; `src/climapp/` según CLAUDE.md; `Settings` que lee `.env.example`.
- **Hecho cuando:** `uv run pytest` corre un test de `Settings` en verde y `ruff` y `mypy` pasan.

### TASK-002 — Inventario de estaciones
- **Estimación:** 3 h · **MoSCoW:** Must · **Responsable:** JM (con JE) · **Depende de:** TASK-004
- Comando que reporta, por estación, el periodo, los días válidos, la correlación por pares y los posibles duplicados (r ≥ 0,99 o días idénticos), con salida en `DATA_DIR/derived/inventory.json`.
- **Hecho cuando:** tests con fixtures sintéticos detectan un duplicado plantado, y el informe real coincide con ADR-004.

### TASK-003 — Lectura del contador y limpieza
- **Estimación:** 3 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-001
- Lector de las dos exportaciones (xls y csv con coma decimal ambigua) y cálculo de incrementos, ignorando descensos y aumentos > 40 mm en 10 min.
- **Hecho cuando:** hay tests de reinicio, pico, coma decimal y valor vacío.

### TASK-004 — Tabla diaria de estaciones
- **Estimación:** 3 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-003
- `DailyPrecip` por día local, con `valid` (≥ 100/144), `imputed=false` y `source_hash`; une las dos exportaciones sin duplicar.
- **Hecho cuando:** los tests cubren el borde de 99/100 lecturas, el cambio de día local y la unión de exportaciones idénticas.

### TASK-005 — Lectores satelitales
- **Estimación:** 2 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-001
- CHIRPS en hoja de cálculo (descarta MIN, PROM, MAX y columnas sin celda) e IMERG Final en CSV (3 puntos → una sola serie).
- **Hecho cuando:** los tests verifican el descarte de filas resumen y la deduplicación de puntos.

### TASK-006 — Objetivo de cuenca
- **Estimación:** 2 h · **MoSCoW:** Must · **Responsable:** JM (con JE) · **Depende de:** TASK-004
- Tres reglas (`any_station`, `basin_mean`, `reference_station`) y sus frecuencias.
- **Hecho cuando:** hay tests por regla con días incompletos, y las frecuencias coinciden con ADR-001 (16,0 / 10,2 / 9,6 %).

### TASK-007 — Líneas base y métricas
- **Estimación:** 3 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-006
- Climatología (día del año ±15) y persistencia; POD, FAR, CSI, Brier, AUC y calibración; exclusión de días imputados.
- **Hecho cuando:** hay tests con casos calculados a mano y un test de que lo imputado no entra.

### TASK-008 — Variables y random forest
- **Estimación:** 4 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-005, TASK-007
- Agregados de la cuenca (media, máx. y desviación en t, t-1, t-2), acumulado de 3 días, satélite y estacionalidad; partición temporal; calibración isotónica; comparación con estaciones individuales.
- **Hecho cuando:** un test de fuga verifica que ninguna fecha de prueba aparece en entrenamiento, y las métricas quedan en `DATA_DIR/derived/evaluation.json`.

### TASK-009 — IMERG Early y Final de 2025 a hoy (R11)
- **Estimación:** 3 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-005
- Descarga con Earthdata (`EARTHDATA_TOKEN`) de `GPM_3IMERGDE` y `GPM_3IMERGDF` para la celda; cálculo de sesgo y correlación.
- **Hecho cuando:** `evaluation.json` incluye `imerg_final_vs_early`, con tests sobre series sintéticas.

### TASK-010 — Variante operativa (estaciones + Early)
- **Estimación:** 3 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-008, TASK-009
- Mismo pipeline, solo con variables disponibles al día siguiente; evaluado aparte (`rf_operational`).
- **Hecho cuando:** un test verifica que no usa IMERG Final, y la evaluación queda publicada.

### TASK-011 — Cliente Muse y fallback
- **Estimación:** 2 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-001
- SDK `openai` con `base_url`, modelo y esfuerzo desde `Settings`; respuestas grabadas con `DEMO_FALLBACK=1`.
- **Hecho cuando:** los tests con un cliente falso cubren los parámetros enviados y el fallback.

### TASK-012 — Comprobaciones deterministas
- **Estimación:** 3 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-011
- Esquema, cifras iguales, herramientas permitidas, `finish_reason == "stop"` y contenido no vacío (ADR-002).
- **Hecho cuando:** hay un test por motivo de rechazo.

### TASK-013 — Juez y bucle de 3 intentos
- **Estimación:** 3 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-012
- Juez con `reasoning_effort=medium`; reintentos con los motivos anteriores; `requiere_revision_humana` tras el tercer fallo.
- **Hecho cuando:** los tests cubren aprobación al primer intento, al tercero y el paso a revisión humana.

### TASK-014 — Confianza por código
- **Estimación:** 2 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-002
- Grupos de estaciones con r ≥ `STATION_GROUP_MIN_R`, que cuentan como una fuente; puntaje con desglose.
- **Hecho cuando:** un test de propiedades verifica que duplicar una estación correlacionada no sube la confianza, y la función es pura.

### TASK-015 — API de pronóstico y evaluación
- **Estimación:** 2 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-008
- `GET /forecast` y `GET /evaluation` según `openapi.yaml`, sobre artefactos precalculados.
- **Hecho cuando:** hay tests de contrato contra el esquema OpenAPI, de los casos 503 y `stale`, y de que el aviso siempre está presente.

### TASK-016 — API de reportes
- **Estimación:** 3 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-013, TASK-014
- `POST /reports` (202 asíncrono, EXIF eliminado, polígono de la cuenca), `GET /reports` y `GET /reports/{id}`.
- **Hecho cuando:** hay tests de contrato, fuera de cuenca, foto > 5 MB y EXIF eliminado.

### TASK-017 — Vista de pronóstico y formulario
- **Estimación:** 4 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-015, TASK-016
- Jinja2 + HTMX, mobile-first; aviso "no es alerta oficial" con enlace; formulario con sondeo de estado.
- **Hecho cuando:** hay tests HTTP del HTML (aviso presente y estados) y una revisión manual en 360 px.

### TASK-018 — Mapa con reportes y acierto
- **Estimación:** 3 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-017
- Leaflet con OSM (atribución ODbL), reportes verificados y resultado diario.
- **Hecho cuando:** un test verifica que el HTML incluye la atribución y los datos del día.

### TASK-019 — Reproducción histórica para la demo
- **Estimación:** 3 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-017, TASK-020 (evento elegido)
- `replay_date` de punta a punta con `DEMO_FALLBACK=1`, con el indicador "reproducción histórica".
- **Hecho cuando:** la demo corre sin red, con un test end-to-end.

### TASK-020 — Validación de SUPUESTOS
- **Estimación:** 2 h · **MoSCoW:** Must · **Responsable:** JM · **Depende de:** — (2026-10-30, 12:00)
- Confirmar o corregir SP-1 a SP-8 (PRD), la regla del objetivo, el umbral de agrupación y el evento de la demo.
- **Hecho cuando:** el PRD y los ADR están actualizados, sin SUPUESTOS resueltos que sigan marcados.

### TASK-021 — Set de evaluación de reportes
- **Estimación:** 3 h · **MoSCoW:** Should · **Responsable:** JM · **Depende de:** TASK-012
- Al menos 30 reportes sintéticos etiquetados (válidos, con cifras falsas, sin evidencia, fuera de cuenca); tasa de aprobación y costo por reporte (NFR-3).
- **Hecho cuando:** el informe reproducible queda en `eval-harness/`.

### TASK-022 — Explicación verificada del pronóstico
- **Estimación:** 2 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-013
- Muse explica el pronóstico; la compuerta exige que las cifras coincidan.
- **Hecho cuando:** un test verifica que una cifra alterada se rechaza y que `explanation=null` si no pasa.

### TASK-023 — Día local desde IMERG cada media hora
- **Estimación:** 4 h · **MoSCoW:** Could · **Responsable:** JE · **Depende de:** TASK-009

### TASK-024 — Containerfile con Podman
- **Estimación:** 2 h · **MoSCoW:** Could · **Responsable:** JE · **Depende de:** TASK-017

## Después del congelamiento (2026-11-03 → 2026-11-04)
### TASK-025 — QA hacia el gate 4
- **Estimación:** 4 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** sprint cerrado
- Cobertura (≥ 85 % en el núcleo, ≥ 70 % global), SAST, gitleaks y 0 bugs CRITICAL/HIGH.

### TASK-026 — Video de demo de 3 min
- **Estimación:** 3 h · **MoSCoW:** Must · **Responsable:** JE + JM · **Depende de:** TASK-019
- Solo funciones construidas en el evento (R10).

### TASK-027 — Entrega
- **Estimación:** 1 h · **MoSCoW:** Must · **Responsable:** JE · **Depende de:** TASK-025, TASK-026
- Enviar antes de las 18:00 hora Cali del 2026-11-04 (límite: 21:00).

## Won't (v1)
Sequía e incendios · audio · cuentas · notificaciones · app nativa · plataforma histórica · investigadores · reentrenamiento automático.
