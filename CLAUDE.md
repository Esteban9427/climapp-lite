# ClimApp Lite — instrucciones para asistentes de código

Pronóstico de lluvia ≥20 mm para mañana en la cuenca del río Pance, con reportes ciudadanos verificados. **No es una alerta oficial.** Contexto completo en `docs/PRD.md` y en las decisiones de `docs/adr/`.

## Estructura
```
src/climapp/
  data/          lectura de crudos, limpieza y tabla diaria (ADR-004)
  forecast/      variables, RF, líneas base, evaluación (ADR-001)      ← núcleo
  verification/  cliente Muse, compuerta, juez, confianza (ADR-002)    ← núcleo
  api/           FastAPI: rutas según docs/openapi.yaml
  web/           Jinja2 + HTMX + Leaflet (ADR-005)
tests/           espejo de src/; fixtures pequeños en tests/fixtures/
```

## Comandos
```bash
uv sync
uv run pytest --cov=climapp --cov-report=term-missing
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run uvicorn climapp.api.main:app --reload
```

## Reglas (obligatorias)
1. **TDD**: primero un test en rojo, luego el código mínimo, luego refactor. Ningún cambio en `src/` sin un test que falle antes.
2. **Nada hardcodeado**: URLs, modelos, umbrales, rutas y fechas salen de la configuración (`pydantic-settings`, `.env`). Los umbrales científicos llevan su fuente o la marca SUPUESTO en el docstring.
3. **Funciones de ≤ 30 líneas** con una sola responsabilidad.
4. **Sin `print`**: usar `structlog` con eventos en JSON (`log.info("report.verified", report_id=..., attempts=...)`).
5. **Tipado completo**: `mypy --strict` en `src/`. Sin `Any` salvo en la frontera con librerías externas.
6. **Docstrings** en toda función o clase pública: qué hace, argumentos, retorno y excepciones.
7. **Sin `except Exception` ni `except:`**: capturar excepciones concretas y relanzarlas con contexto.
8. **La confianza la calcula código, nunca el LLM** (ADR-002). La compuerta de verificación no se salta, ni siquiera en la demo.
9. **Datos**: nunca versionar datos crudos ni derivados (`data/`, `*.xls`, `*.csv`, etc.). Los fixtures de `tests/fixtures/` son sintéticos.
10. **Sin nombres ni coordenadas de estaciones** en código, tests, docs ni commits: usar `EST-A`…`EST-D` (ADR-004).
11. **Secretos** solo en `.env`; `.env.example` sin valores secretos.
12. **Commits** convencionales en español, dos por tarea: `test(task-NNN)` con el test en rojo y luego `feat(task-NNN)` (o `fix`) con el código en verde, como evidencia de TDD (DoD §1) y del trabajo durante el evento (R10). Cada commit lleva solo las rutas de su tarea; nunca `git add -A` ni `--no-verify`.
13. **Revisión**: antes de un merge que toque el núcleo o el contrato de la API, revisión en solo lectura con `muse exec --model muse-spark-1.3 --contributor-mode off` (ADR-003).
14. **Contribuciones**: al cerrar una tarea, agregar una línea a "Construido durante el evento" en el README.
15. **Contenedores**: Podman, nunca Docker.
