# Sprint 1 — 2026-10-30 → 2026-11-02

> Objetivo: la primera rebanada vertical de punta a punta (datos → pronóstico evaluado → reporte verificado y explicado → web con aviso → demo reproducible).
> Capacidad comprometida: JE 32 h (límite del 80 % de G3; el foco declarado es del 85 %) y JM 8 h (100 %, excepción aprobada; declaradas por JM el 2026-10-29, por confirmar). Línea de corte aprobada el 2026-10-29: ver [`../backlog.md`](../backlog.md). Arranque en `DATA_PLAN=plan_b_earthdata`. El congelamiento se aplica al cierre del lunes 2-nov (festivo).

## Spec Gate: ✅ APROBADO (2026-10-29)
| Verificación | Resultado | Evidencia |
|--------------|-----------|-----------|
| SPEC (perfil hackathon: G1 + G2 + G3) | **7/7** | Checks de `core/profiles/hackathon/gates/spec.yaml` corridos con `forge_core.gate.docs` sobre este repo (el CLI `forge gate check spec --path` exige un `metrics.json` de FORGE, que no se versiona aquí) |
| G1, G2 y G3 estándar | **12/12** | Mismos checks de `core/gates/gate{1,2,3}.yaml` |
| `docs/openapi.yaml` | válido | `openapi-spec-validator` |
| Revisión independiente | atendida | [`../reviews/spec-gate.md`](../reviews/spec-gate.md) |
| Nombres de estaciones y datos en git | 0 | grep con `.forbidden-terms` sobre todo el historial; gitleaks limpio |

Aprobado por: el equipo (decisión del 2026-10-29). Quedan SUPUESTOS abiertos hasta TASK-020.

| Día | JE | JM | Salida verificable |
|-----|----|----|--------------------|
| vie 30 (6 h; JE trabaja en su empleo) | TASK-001, TASK-003, TASK-005 (4,5 h) | TASK-020 (12:00) | Lectura limpia con tests en verde |
| sáb 31 (12 h) | TASK-004, TASK-006, TASK-007, TASK-008, TASK-015 (10 h) | TASK-002 | Tabla diaria, RF y `GET /evaluation` |
| dom 1 (12 h) | TASK-011, TASK-012, TASK-013, TASK-014, TASK-022 (9,5 h) | TASK-021 (cuando TASK-012 esté lista) | Compuerta y explicación con tests |
| lun 2 (10 h, festivo) | TASK-016, TASK-017, TASK-018, TASK-019 (8 h) | — | Web móvil con aviso y demo reproducible; **congelamiento al cierre** |

TASK-009 (IMERG Early) vuelve a JE el 2026-10-30 como el primer Should en entrar; TASK-028 (JE, 1 h) la sigue si hay holgura. Si el viernes la velocidad supera la estimada, entran tareas Should en el orden del backlog. TASK-035 (plan B de datos) solo se activa si D-03 no está cerrado el 1-nov.

## Tareas comprometidas
### TASK-001 — Esqueleto del proyecto
- **Estimación:** 1 h
### TASK-002 — Inventario de estaciones (JM)
- **Estimación:** 3 h
### TASK-003 — Lectura del contador y limpieza
- **Estimación:** 2,5 h
### TASK-004 — Tabla diaria de estaciones
- **Estimación:** 2,5 h
### TASK-005 — Lector de CHIRPS
- **Estimación:** 1 h
### TASK-006 — Objetivo de cuenca (regla principal)
- **Estimación:** 1 h
### TASK-007 — Líneas base y métricas
- **Estimación:** 2,5 h
### TASK-008 — Variables y random forest
- **Estimación:** 3 h
### TASK-011 — Cliente Muse y fallback
- **Estimación:** 1,5 h
### TASK-012 — Comprobaciones deterministas
- **Estimación:** 2,5 h
### TASK-013 — Juez y bucle de 3 intentos
- **Estimación:** 2,5 h
### TASK-014 — Confianza por código
- **Estimación:** 1,5 h
### TASK-015 — API de pronóstico y evaluación
- **Estimación:** 1 h
### TASK-016 — API de reportes
- **Estimación:** 2 h
### TASK-017 — Vista de pronóstico, formulario y lista de reportes
- **Estimación:** 3 h
### TASK-018 — Mapa mínimo (marcadores)
- **Estimación:** 1 h
### TASK-019 — Reproducción histórica para la demo
- **Estimación:** 2 h
### TASK-020 — Validación de SUPUESTOS (JM)
- **Estimación:** 2 h
### TASK-021 — Set de evaluación de reportes (JM)
- **Estimación:** 3 h
### TASK-022 — Explicación verificada del pronóstico
- **Estimación:** 1,5 h

## Congelamiento de alcance aplicado — 2026-11-02
- **Fecha y hora:** al cierre del lunes **2026-11-02, 23:59 hora Cali (UTC−05:00)** (`SCOPE_FREEZE_DATE=2026-11-02`). Esta sección se registró el mismo día a las 20:12, antes del cierre.
- **Entró el mismo día como bugfix autorizado (ninguno es una función nueva del producto):**

  | Cambio | Commit (hora Cali) | Por qué |
  |--------|--------------------|---------|
  | Tope de tokens de Muse por tarea (estructurar 3000, juez 4000) | `f49ec96` (18:54) | Con 2000 se cortaba el 24 % de los juicios: respuestas vacías y reportes verdaderos a revisión humana |
  | Fallo A: confianza de las crecientes sin afirmación de lluvia | `5b5fee4` (19:10) | Un falso de desborde en día seco salía "Coincide con los datos" (R28) |
  | Fallo B: `cifra_omitida` en la compuerta | `ed021fd` (19:14) | Un exagerado con "5 metros" se verificaba con `numbers_cited` vacío (R26) |
  | Reintento aparte de los reportes caídos por la API | `47f4d8d` (19:14) | Solo herramienta de evaluación (`eval-harness/run_eval.py`), no código del producto |
  | Fixes de la revisión de Muse (`GET /evaluation` sin 500 con un resumen ilegible; validación de `--run`) | `705b8fe` + `b87cab4` (20:08-20:09) | Revisión en solo lectura, `docs/reviews/TASK-036.md` |

  Cada uno con su test en rojo antes (TDD) y sin cambios en prompts, pesos ni umbrales.
- **También entró el mismo día, como trabajo de las tareas comprometidas TASK-021 y TASK-036 (no es bugfix):** el set y el runner de evaluación (`eval-harness/`), el campo `report_verification` de `GET /evaluation` (`1a74184`, `1fdf32b`) y la publicación de sus resultados (`e11a140`).
- **Regla desde ahora:** solo bugfixes CRITICAL/HIGH, documentación, video y entrega. Cualquier otra cosa va al backlog post-hackathon.
- **Pendiente para Gate 4 (mar 3-nov, TASK-025):**
  - [ ] Cobertura ≥ 85 % en el núcleo (≥ 70 % global).
  - [ ] SAST.
  - [ ] Escaneo de secretos.
  - [ ] 0 bugs CRITICAL/HIGH.
  - [ ] Demo con `DEMO_FALLBACK=1` de punta a punta.

## Backlog post-hackathon
- **BUG-001 (LOW): la API no emite logs en JSON.** Encontrado en el Gate 4 ([`../reviews/gate4.md`](../reviews/gate4.md)). Sin aplicar por el congelamiento de alcance.
  - **Actual:** al levantar la API, los logs salen con el formato de consola de structlog (`2026-11-02 20:17:03 [warning ] explain.muse_error …`), no en JSON como pide la regla 4 de CLAUDE.md y la línea 55 del README.
  - **Causa raíz:** `src/climapp/api/main.py` importa `get_logger` pero nunca llama a `configure_logging()`; solo lo hacen las CLI.
  - **Fix propuesto (TDD):** test en rojo que capture la salida de la app y valide JSON; luego llamar a `configure_logging()` al crear la app (factory o lifespan).
