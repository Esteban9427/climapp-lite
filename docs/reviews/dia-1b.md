# Revisión de Muse Code — día 1b (2026-10-30, tarde)

> **Comando:** `muse exec --model muse-spark-1.3 --contributor-mode off --effort medium "Revisa src/ y tests/ contra CLAUDE.md y docs/dod.md. No edites nada."`
> **Versión:** Muse Code 1.4.14. **Commit revisado:** `ec5c31f` (TASK-015 cerrada).
> **Entorno:** copia de `git ls-files` (sin `data/`, `.env` ni `.forbidden-terms`), sin red. El workspace no era de confianza: Muse leyó `CLAUDE.md` como documento, no como reglas propias.
> **Solo lectura:** `diff -rq` contra una copia previa (excluyendo cachés) sin diferencias.

## Salida (rutas absolutas de la copia reemplazadas por rutas del repo)

Revisión completada, sin editar nada. Alcance: `src/climapp/` (config, logging, api, data, forecast; `verification/` y `web/` son stubs) y `tests/` contra las 15 reglas de `CLAUDE.md` y los 12 puntos de `docs/dod.md`.

## Veredicto

El código existente (data + forecast + api/forecast) cumple casi todas las reglas. Los hallazgos reales son 1 violación de regla, 1 fuga metodológica en líneas base, el contrato de reportes sin implementar y varios bordes sin manejar. Parte de la verificación quedó bloqueada por el entorno (sin git, sin deps completas, sin `.forbidden-terms`).

## Hallazgos (ordenados por importancia)

1. **Reportes sin implementar (DoD §9, regla 8).** `src/climapp/verification/__init__.py` y `src/climapp/web/__init__.py` son stubs de una línea. `docs/openapi.yaml` exige `POST /reports`, `GET /reports` y `GET /reports/{id}`; `src/climapp/api/main.py:125` solo registra `/forecast` y `/evaluation`. El contrato de reportes no se cumple y la compuerta de verificación no existe todavía.
2. **`DEMO_FALLBACK=1` sin efecto (DoD §12).** `demo_fallback` es campo de `Settings` pero nada en `src/` lo lee. Tampoco `scope_freeze_date`, `station_group_min_r`, `earthdata_token`, `muse_*` ni `verify_max_attempts` (esperable mientras verificación está pendiente, pero la demo con fallback no puede funcionar hoy).
3. **Fuga train/valid en líneas base.** `src/climapp/forecast/evaluation.py:139` llama `_baselines(parts["train"] + parts["valid"], ...)` pero el docstring dice "ajustadas solo con entrenamiento". Climatología y persistencia ven los días de validación que luego se usan para fijar umbrales. Prueba (`test`) no está afectada.
4. **Regla 3 violada.** `climatology_probs` en `src/climapp/forecast/baselines.py:22` mide 31 líneas (>30). Todo lo demás en `src/` mide ≤30.
5. **Artefacto corrupto → 500 en vez de 503.** `src/climapp/api/artifacts.py:20` solo convierte `FileNotFoundError` en `ArtifactMissingError`. Un JSON corrupto o con esquema inválido (`json.loads`, `TypeAdapter.validate_json`) propaga `JSONDecodeError`/`ValidationError` fuera de los `except ArtifactMissingError` de `src/climapp/api/main.py:89`, rompiendo el formato `{code, message}`.
6. **Bordes sin documentar ni manejar.** `run_evaluation` (`src/climapp/forecast/evaluation.py:186`) hace `min(...)` sobre `parts["test"]` vacío → `ValueError` no documentado; `test_period.end` usa `config.periods.test_end` en vez del máximo real (inconsistente con `start`). `cli.py:119` indexa `records[-1]` que falla si no hay emisiones.
7. **`DAYS_PER_YEAR` inconsistente.** `features.py:19` usa 365.25 y `baselines.py:8` usa 365. El 29-feb queda a distinta distancia según el módulo.
8. **Regla 6, menores.** La función anidada `event` en `src/climapp/forecast/dataset.py:82` no tiene docstring; las rutas públicas `forecast`, `evaluation` y `_to_forecast` en `src/climapp/api/main.py` llevan docstring de una línea sin Args/Returns.
9. **Espejo de tests incompleto.** No hay `test_dataset.py` ni `test_publish.py` (`build_samples`, `split_samples`, `forecast_records` solo se cubren indirectamente vía `test_cli.py`/`test_evaluation.py`); `tests/fixtures/` solo tiene `.gitkeep` (mitigado: factories sintéticas en memoria). Menor: `STALE_AFTER = 24h` hardcodeado en `src/climapp/api/main.py:27` (regla 2, discrecional).
10. **Posible roce con regla 10.** `.env.example` contiene `EXPORT_PANCE_RAWDATA`, `ExportJMN_Pance` en `STATION_EXPORTS`/`CHIRPS_FILES`. Son nombres de archivo, no de estación, y `JMN` podría ser nombre real; no puedo confirmarlo sin `.forbidden-terms` (no existe localmente, correcto según DoD §7). Revisar cuando esté disponible.

## Verificado que cumple

Sin `print`, sin `except Exception`/`except:`, sin `Any` en `src/`, `ruff check` y `ruff format --check` en verde, `gitleaks detect --no-git` limpio, logging `structlog` JSON (`daily.merged`, `daily.written`, `daily.done`, `forecast.published`, `api.error`), umbrales con marca SUPUESTO o referencia ADR, `Settings` sin defaults ocultos, README con entradas del evento, sin datos versionados.

## No verificable en este entorno (no es defecto del código)

Sin repo git aquí: TDD rojo→verde, commits en español y revisión pre-merge (reglas 1, 12, 13; DoD §1, §8, §10). `mypy src` bloqueado (falta `pydantic` en el intérprete del sistema y `uv sync` sin red); `pytest` completo bloqueado (faltan `structlog`, `xlrd`, `openpyxl`, `sklearn`): el subconjunto instalable pasa con **85 passed**, y el resto ni siquiera importa. Cobertura ≥85 %/≥70 % pendiente de entorno con red.

## Atención
| # | Hallazgo | Decisión |
|---|----------|----------|
| 1 | Reportes y compuerta sin implementar | Esperado: TASK-011 a TASK-014 (domingo) y TASK-016 (lunes) |
| 2 | `DEMO_FALLBACK` sin efecto | Esperado: TASK-011 (domingo) y TASK-019 (lunes). Hoy la demo no depende del LLM: `GET /forecast?replay_date=2024-12-31` funciona sin red |
| 3 | Las líneas base se ajustan con la validación, que luego fija el umbral de la climatología | **Pendiente de decisión del equipo.** Solo afecta POD, FAR y CSI de la climatología (no su AUC ni su Brier, que salen del ajuste ≤ 2022 sobre la prueba). Recalcular sería otro ajuste tras ver la prueba, que la condición de ADR-001 §1 excluye; se corrigió el docstring, que decía "solo con entrenamiento" |
| 4 | `climatology_probs` de 31 líneas | **Atendido**: se extrajo el conteo por día del año. El chequeo local de la DoD ahora cuenta también el docstring |
| 5 | Artefacto corrupto → 500 | **Atendido** con test: 503 `artefacto_invalido` |
| 6 | Prueba vacía o sin emisiones | **Atendido** con test: `ValueError` claro si no hay días de prueba; sin esa condición siempre hay emisiones, así que `records[-1]` no puede fallar |
| 7 | `DAYS_PER_YEAR` con dos valores | **Atendido**: son dos conceptos distintos y ahora tienen nombres distintos (`DOY_CYCLE`, `TROPICAL_YEAR_DAYS`) |
| 8 | Docstrings incompletos | **Atendido** en las rutas públicas y en la función anidada |
| 9 | Sin `test_dataset.py` ni `test_publish.py`; `STALE_AFTER` fijo | Cobertura de esos módulos del 97 % y el 100 % vía otros tests; `STALE_AFTER` es una regla del contrato (24 h, `docs/api-contracts.md`), comentada como tal |
| 10 | `JMN` en nombres de archivo | No es el nombre de una estación (son las iniciales de un integrante del equipo, que figura en el README); `git grep -niEf .forbidden-terms` = 0 |

Tras los cambios, `climapp-train` produce artefactos idénticos byte a byte a los de la corrida oficial (verificado con `cmp`).
