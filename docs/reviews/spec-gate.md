# Revisión del Spec Gate — Muse Code (solo lectura)

> **Comando:** `muse exec --model muse-spark-1.3 --contributor-mode off --effort medium "Revisa docs/adr y docs/backlog.md: contradicciones, tareas >4 h, dependencias rotas. No edites nada."`
> **Herramienta:** Muse Code 1.4.14 (herramienta previa al evento; no forma parte del entregable).
> **Fecha:** 2026-10-29.
> **Entorno:** copia de los archivos versionados del repo, **sin `data/` ni `.env`**, para que el agente no pudiera leer datos crudos. Un diff posterior confirmó que no editó nada.
> **Salida:** literal; solo se cambiaron las rutas absolutas de la copia por rutas relativas. La sección "Atención" al final es del equipo.

---

Revisión de [docs/adr](../../docs/adr) y [docs/backlog.md](../../docs/backlog.md). No edité nada.

## Contradicciones ADR ↔ backlog

1. Evaluación sin EST-B: [ADR-001 §6](../../docs/adr/ADR-001-modelo-objetivo-lineas-base.md) la redacta como obligatoria ("se evalúa con y sin EST-B y se reportan ambas"). En backlog es Should ([TASK-029](../../docs/backlog.md)) y queda fuera del compromiso de 32 h. El Must no cubre lo que el ADR exige.
2. Umbral de agrupación: [ADR-002 §4](../../docs/adr/ADR-002-muse-spark-verificacion.md) fija r ≥ 0,8. [TASK-002](../../docs/backlog.md) usa `STATION_GROUP_MIN_R` sin valor por defecto documentado. Si el default no es 0,8, hay contradicción.
3. `max_tokens`: [ADR-002](../../docs/adr/ADR-002-muse-spark-verificacion.md) fija 2000 por tarea. [TASK-011](../../docs/backlog.md) pide `max_tokens ≥ 2000`. Diferencia menor, pero el test aceptaría un valor que el ADR no autoriza.
4. Orden de la compuerta: [ADR-002 §3](../../docs/adr/ADR-002-muse-spark-verificacion.md) define un orden (finish_reason → contenido → esquema → cifras → herramientas). [TASK-012](../../docs/backlog.md) lista otro orden. Solo importa si el primer motivo reportado es contrato.
5. Plan B de datos sin tarea: [ADR-004 §5](../../docs/adr/ADR-004-datos.md) exige decisión el 2026-11-01 (si no hay autorización, modelo y demo solo con CHIRPS + IMERG Early, objetivo sobre CHIRPS). Ninguna tarea del backlog implementa ese plan B ni aparece la fecha 1-nov en el plan por día. [TASK-006](../../docs/backlog.md) y [TASK-008](../../docs/backlog.md) asumen estaciones.
6. Calibración Must depende de Should: [ADR-002 §4](../../docs/adr/ADR-002-muse-spark-verificacion.md) dice que los pesos de confianza se calibran en el eval-harness. El eval-harness es [TASK-021](../../docs/backlog.md) (Should, JM). La confianza ([TASK-014](../../docs/backlog.md), Must) quedaría sin calibrar en el compromiso.
7. Criterio dudoso en [TASK-006](../../docs/backlog.md): pide tests con días de 1, 2 y 4 estaciones y que "la frecuencia coincida con ADR-001 (10,2 %)". El 10,2 % es la frecuencia histórica [INV], no reproducible con fixtures sintéticos de 3 casos.
8. Estado condicional: [TASK-009](../../docs/backlog.md) figura como "Should (Must si se aprueba sin la propuesta)". La propuesta está pendiente de confirmación. El alcance Must queda ambiguo hasta que se confirme.

## Tareas > 4 h

Ninguna estimación nominal supera las 4 h. Dos tocan el límite y una lo anticipa:

- [TASK-023](../../docs/backlog.md): 4 h (Could).
- [TASK-025](../../docs/backlog.md): 4 h (Must post-congelamiento).
- [TASK-009](../../docs/backlog.md): estimada en 3 h, pero su propio texto admite "si la descarga pasa de 4 h, se parte...". Eso rompe la regla de cabecera ("ninguna tarea dura más de 4 h") si el tiempo de descarga cuenta como duración.

## Dependencias rotas o frágiles

1. [TASK-002 → TASK-004](../../docs/backlog.md): JM (sáb 31) depende de JE (sáb 31, misma jornada: TASK-004, 006, 007, 008, 015). El orden intradía no está explicitado. JM queda bloqueado hasta que JE termine TASK-004.
2. [TASK-025](../../docs/backlog.md) depende de "sprint cerrado". No es un ID de tarea. Es ambiguo.
3. Hueco de numeración: falta TASK-010 (el salto 008 → 011 viene de la tarea eliminada según "Cambios"). Ninguna dependencia apunta a TASK-010, así que no hay referencia rota hoy. Conviene verificar que no se reutilice el número.
4. Cadena crítica sobre supuesto no confirmado: capacidad de JM (8 h) se confirma el 30-oct 12:00. [TASK-020](../../docs/backlog.md) (JM, Must) resuelve SP-1–SP-8, `TARGET_RULE`, umbral de agrupación y evento demo. [TASK-019](../../docs/backlog.md) (lun 2) depende de ese evento. Si JM no confirma, cae la cadena de SUPUESTOS.
5. Dependencias intradía implícitas (orden correcto solo si se ejecutan en el orden listado): dom 1 (012 → 013 → 014; 013 → 022) y lun 2 (016 → 017 → 019; 017 → 018). Funcionan únicamente en secuencia estricta.

---

## Atención del equipo (2026-10-29)
| Hallazgo | Decisión | Cambio |
|----------|----------|--------|
| C1 EST-B obligatoria en el ADR y Should en el backlog | Aceptado | ADR-001 §6 separa la robustez por diseño (Must) del informe comparativo (Should, TASK-029) |
| C2 `STATION_GROUP_MIN_R` sin valor por defecto | Aceptado | TASK-002 documenta 0,8 (SUPUESTO), igual que `.env.example` |
| C3 `max_tokens ≥ 2000` frente a 2000 | Aceptado | TASK-011: `max_tokens = MUSE_MAX_TOKENS` (2000); la configuración rechaza < 2000 |
| C4 Orden de la compuerta | Aceptado | TASK-012 sigue el orden de ADR-002 §3, con un test del orden |
| C5 Plan B de datos (D-03) sin tarea | Aceptado | Nueva TASK-035 contingente; decisión de D-03 el dom 1 |
| C6 Confianza Must que depende de una calibración Should | Aceptado | ADR-002 y TASK-014: pesos fijos SUPUESTO en v1; calibración Should (TASK-021) |
| C7 Criterio de 10,2 % no reproducible con fixtures | Aceptado | TASK-006 separa los tests sintéticos de la verificación manual sobre datos reales |
| C8 Estado condicional de TASK-009 | Se mantiene | Depende de que el equipo confirme la línea de corte; se resuelve con esa confirmación |
| T TASK-009 podría pasar de 4 h | Aceptado | Se estima el volumen primero; si pasa de 4 h, se parte en 009a/009b antes de empezar; la descarga desatendida no cuenta como horas |
| D1 TASK-002 bloqueada el mismo día | Aceptado | Orden explícito: TASK-004 por la mañana y luego TASK-002 |
| D2 TASK-025 depende de "sprint cerrado" | Aceptado | Depende de todas las Must comprometidas |
| D3 Hueco de TASK-010 | Aceptado | Anotado: el ID 010 no se reutiliza |
| D4 Cadena sobre los SUPUESTOS de JM | Aceptado | TASK-020: si no hay respuesta antes de las 18:00 del 30-oct, se mantienen los SUPUESTOS y JE elige el evento con una regla explícita |
| D5 Dependencias intradía | Aceptado | El backlog declara que el orden de cada día es el de la lista |
