# Revisión de Muse Code — día 1 (2026-10-30)

> **Comando:** `muse exec --model muse-spark-1.3 --contributor-mode off --effort medium "Revisa src/ y tests/ contra CLAUDE.md y docs/dod.md. No edites nada."`
> **Versión:** Muse Code 1.4.14. **Commit revisado:** `583473b`.
> **Entorno:** copia de `git ls-files` (sin `data/`, `.env` ni `.forbidden-terms`), sin red. Muse avisó que el workspace no era de confianza, así que no cargó `CLAUDE.md` como reglas del agente; lo leyó como documento a revisar.
> **Solo lectura:** `diff -rq` contra una copia previa solo muestra cachés (`.venv`, `__pycache__`, `.pytest_cache`, `.ruff_cache`) creados por sus intentos de correr las herramientas; ningún archivo versionado cambió.

## Salida (rutas absolutas de la copia reemplazadas por rutas del repo)

Revisión completada, sin editar nada. Alcance: `src/climapp/` (config, logging, data con 5 módulos) y `tests/` (7 archivos) contra las 15 reglas de `CLAUDE.md` y los 12 puntos de `docs/dod.md`.

## Veredicto

El código implementado cumple las reglas. Los puntos no verificables lo son por límites del entorno, no por defectos del código.

## CLAUDE.md — regla por regla

| Regla | Estado |
|---|---|
| 1. TDD (test en rojo primero) | No verificable aquí: el workspace no es un repo git, no hay historial que auditar |
| 2. Nada hardcodeado | Cumple. Todo sale de `Settings`: [config.py](src/climapp/config.py) no tiene valores por defecto ocultos y el test `test_missing_key_is_rejected` lo blinda. Constantes en `src/` son de formato de archivo (`HEADER`, `TIMESTAMP_FORMAT`) o técnicas documentadas (`FLOAT_TOLERANCE_MM`, `PRECIP_DECIMALS`) |
| 3. Funciones ≤ 30 líneas | Cumple, verificado por AST: ninguna función en `src/` supera 30 líneas |
| 4. Sin `print`, structlog JSON | Cumple. Cero `print`; `daily.merged`, `daily.written` y `daily.done` con kwargs en [daily.py](src/climapp/data/daily.py:246) y [cli.py](src/climapp/data/cli.py:39) |
| 5. Tipado completo, `mypy --strict` | Por inspección cumple (todo anotado, sin `Any`). `mypy` no ejecutable aquí: falla por `pydantic` ausente en el intérprete del sistema y sin red para `uv sync` |
| 6. Docstrings públicas | Cumple. Toda función/clase pública documenta qué, args, retorno y excepciones; incluso las privadas tienen docstring |
| 7. Sin `except Exception` | Cumple. Cero ocurrencias; solo `ValueError` concreto relanzado con contexto (`raise ... from err`) en [chirps_reader.py](src/climapp/data/chirps_reader.py:102), [station_reader.py](src/climapp/data/station_reader.py:84) |
| 8. Confianza la calcula código | Cumple trivialmente: `verification/` es solo un stub, no hay llamada a LLM en `src/` |
| 9. Sin datos versionados | Cumple. `.gitignore` excluye `data/`, `*.xls/csv` con excepción para `tests/fixtures/` (solo tiene `.gitkeep`); fixtures generados en memoria con openpyxl/xlwt |
| 10. Sin nombres/coordenadas | Cumple en lo verificable. Solo `EST-A…EST-C` y `raw-a`; fechas/valores sintéticos. El grep de coordenadas solo dio ruido flotante (`821.20000000000005`), no coordenadas |
| 11. Secretos en `.env` | Cumple. Solo existe `.env.example`, sin valores; `gitleaks detect --no-git`: `no leaks found` |
| 12. Commits | No verificable: sin repo git en este workspace |
| 13. Revisión pre-merge | N/A: `api/`, `forecast/`, `verification/`, `web/` son stubs de una línea; no hay núcleo ni contrato implementado que revisar |
| 14–15. README, Podman | README tiene la sección con 6 entradas al día; nada que decir de contenedores |

## docs/dod.md — puntos con riesgo

- **P2 (pytest + cobertura)**: no ejecutable aquí (sin red, `.venv` sin dependencias). Queda pendiente correr `uv run pytest --cov=climapp` en un entorno con red.
- **P3**: `ruff check` y `ruff format --check` pasan (verificado con ruff del sistema: `All checks passed`, 41 archivos). `mypy src` pendiente por lo dicho arriba.
- **P5**: umbrales con marca SUPUESTO o referencia ADR en docstrings y `config.py`. Sin hallazgos.
- **P7**: `.forbidden-terms` no existe localmente (correcto: no se versiona), así que el grep oficial no puede correrse; revisión manual limpia.
- **P9 (contrato API)**: no existe test de contrato y `api/` es stub. Esperable a día 1, pero debe añadirse cuando se implemente `/forecast` y `/reports`.

## Observación menor (no bloquea)

[test_station_reader.py](tests/data/test_station_reader.py:37) usa `"EST-A"` como nombre *crudo* en los CSV sintéticos, mientras [test_daily.py](tests/data/test_daily.py:38) y [test_cli.py](tests/data/test_cli.py:14) usan `"raw-a"` + mapa, que es el modelo real (crudo → `load_station_map` → `EST-x`). No filtra nada real, pero el lector crudo nunca debería ver un `EST-x` como entrada; convendría unificar los fixtures a nombres crudos.

Nada fue modificado: solo lecturas y comandos de solo lectura (`grep`, `ruff`, `gitleaks`, intentos de `pytest`/`mypy` que el entorno sin red impidió completar).

## Atención
| Punto | Decisión |
|-------|----------|
| Reglas 1 y 12 (TDD y commits) no verificables sin git | Verificado en el repo: cada tarea tiene un commit `test(...)` en rojo antes del `feat(...)` |
| P2, P3 (`pytest`, `mypy`) no ejecutables sin red | Corridos en el repo: tests, cobertura, `ruff` y `mypy --strict` en verde (ver el resumen del día) |
| P7 (`.forbidden-terms`) | Corrido en el repo antes de cada commit: 0 resultados |
| P9 (test de contrato) | Esperado: llega con TASK-015 y TASK-016 |
| Observación: `EST-A` como nombre crudo en `test_station_reader.py` | **Atendida**: los fixtures del lector usan nombres crudos (`raw-a`…), y el paso a `EST-x` solo ocurre con el mapa |
