# ADR-003: Flujo constructor/revisor

- **Estado:** Aceptado
- **Fecha:** 2026-10-29

## Contexto
Durante el evento se construye con asistentes de programación, que son **herramientas previas al evento y no forman parte del entregable** (README). Se necesita una segunda mirada independiente antes de integrar cambios importantes, sin que el revisor pueda modificar el código.

## Decisión
1. **Constructor:** Claude Code implementa cada tarea con TDD (test en rojo → código → refactor) en una rama `task/TASK-NNN-<slug>`.
2. **Revisor:** Muse Code revisa en **solo lectura** antes de cada merge importante (cualquier cambio en `src/climapp/forecast/`, `src/climapp/verification/`, `openapi.yaml` o el esquema de datos):
   ```bash
   muse exec --model muse-spark-1.3 --contributor-mode off "<prompt de revisión del diff>"
   ```
   Siempre con el modelo estándar y `--contributor-mode off`. La salida se guarda en `docs/reviews/TASK-NNN.md`.
3. **Merge:** a `main` solo con tests en verde, ruff y mypy limpios, y la revisión atendida o justificada por escrito.
4. **Commits:** convencionales en español, uno por tarea. Nunca `git add -A` ni `--no-verify`.
5. **Trazabilidad para el jurado:** cada tarea cerrada agrega una línea a "Construido durante el evento" en el README.

## Consecuencias
- Un revisor de otro proveedor reduce los puntos ciegos de un único asistente.
- Cada revisión cuesta tiempo (unos 10 min por merge, SUPUESTO), pero solo se exige en las rutas del núcleo.
