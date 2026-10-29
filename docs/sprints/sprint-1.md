# Sprint 1 — 2026-10-30 → 2026-11-02

> Objetivo: la primera rebanada vertical de punta a punta (datos → pronóstico evaluado → reporte verificado y explicado → web con aviso → demo reproducible).
> Capacidad comprometida: JE 32 h (límite del 80 % de G3; el foco declarado es del 85 %) y JM 8 h (100 %, excepción aprobada; SUPUESTO hasta el 30-oct a las 12:00). Línea de corte aprobada el 2026-10-29: ver [`../backlog.md`](../backlog.md). Arranque en `DATA_PLAN=plan_b_earthdata`. El congelamiento se aplica al cierre del lunes 2-nov (festivo).

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
| vie 30 (6 h; JE trabaja en su empleo) | TASK-001, TASK-003, TASK-005 (4,5 h) | TASK-020 (12:00); TASK-009 (cuando JM tenga tiempo) | Lectura limpia con tests en verde |
| sáb 31 (12 h) | TASK-004, TASK-006, TASK-007, TASK-008, TASK-015 (10 h) | TASK-002 | Tabla diaria, RF y `GET /evaluation` |
| dom 1 (12 h) | TASK-011, TASK-012, TASK-013, TASK-014, TASK-022 (9,5 h) | — | Compuerta y explicación con tests |
| lun 2 (10 h, festivo) | TASK-016, TASK-017, TASK-018, TASK-019 (8 h) | — | Web móvil con aviso y demo reproducible; **congelamiento al cierre** |

TASK-009 (IMERG Early, JM) corre en paralelo. TASK-028 (JE, 1 h) entra cuando TASK-009 esté lista y haya holgura. Si el viernes la velocidad supera la estimada, entran tareas Should en el orden del backlog. TASK-035 (plan B de datos) solo se activa si D-03 no está cerrado el 1-nov.

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
### TASK-009 — Descarga de IMERG Early V07 2000→hoy (JM)
- **Estimación:** 3 h
### TASK-022 — Explicación verificada del pronóstico
- **Estimación:** 1,5 h
