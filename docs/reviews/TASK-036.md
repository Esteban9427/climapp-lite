# Revisión de Muse — TASK-036 (rama task-036-evaluation-api)

> **Comando:** `muse exec --model muse-spark-1.3 --contributor-mode off --effort medium "Revisa en solo lectura la rama task-036-evaluation-api frente a main [...] Separa bugs de mejoras. No edites nada."` (pedido completo en la sesión). Fecha: 2026-11-03. Commits revisados: `feec236`..`e11a140`.

## Respuesta de Muse (literal)

Revisión en solo lectura de `task-036-evaluation-api` frente a `main`. No edité nada. Veredicto: sin bugs graves; la compuerta no se puede saltar por los caminos nuevos y el contrato es coherente. Hay 2 bugs leves y varias mejoras.

## Bugs

1. `GET /evaluation` puede dar 500 en vez de `null`. [artifacts.py](src/climapp/api/artifacts.py): `_read` solo convierte `FileNotFoundError` en `ArtifactMissingError`; si `REPORT_EVAL_FILE` apunta a un directorio o hay un error de permisos (`IsADirectoryError`, `PermissionError`), la excepción escapa de [load_report_eval()](src/climapp/api/artifacts.py) y la ruta devuelve 500, contra lo que promete el contrato ("`null` si falta o es inválido"). Severidad baja; capturar `OSError` lo cierra.
2. `publish_summary --run` sin validar formato. [publish_summary.py](eval-harness/publish_summary.py): `tuple(r.split(":"))` y el desempaquetado en `for run, structure, judge` revientan con `ValueError` si el valor no trae exactamente dos `:`. Herramienta interna, severidad baja; validar el formato y fallar con mensaje.

## Verificado sin hallazgos

- **Compuerta no saltable.** `cifra_omitida` vive en `_content_reasons` ([checks.py](src/climapp/verification/checks.py)); con motivos, `parsed` es `None`, el juez ni corre y `run_gate` termina en `requiere_revision_humana` ([test dedicado](tests/verification/test_gate.py)). [reports.py](src/climapp/verification/reports.py) siempre pasa `source_text`; explicación y juez usan el default `None`, correcto porque sus cifras se controlan por `cited_numbers`. `feedback_message` es genérico, así que el motivo nuevo llega al reintento sin tocar prompts. Sin bypass: citada-con-unidad → `cifra_no_coincide` (`allowed_numbers` vacío); omitida → `cifra_omitida`.
- **Horas, fechas y prefijos.** Sonda directa del regex: `4:10`, `14/05/2024`, `2026-11-03`, `SP-10`, `3 horas`, `10 min` no matchean; `10 min` está a salvo por `(?!\w)`. Sin falsos positivos de `m` en `mas`, `millones`, `minutos`.
- **Confianza de no-crecida intacta.** `_expects_rain` devuelve `report_rain` cuando no es `None`, y `_station_sources` solo cambia con `None`, que [evidence.py](src/climapp/verification/evidence.py) solo produce para `crecida`+`ninguna`. El resto de reportes calcula igual que antes; nivel y satélite/pronóstico para crecidas sin afirmación concuerdan si indican lluvia, como pide la tarea.
- **Tokens por tarea.** Config, [.env.example](.env.example), [muse.py](src/climapp/verification/muse.py) (`max_tokens[task]`) y tests coherentes; `MUSE_MAX_TOKENS` solo sobrevive en texto histórico (ADR "antes era", backlog tachado).
- **Contrato.** [openapi.yaml](docs/openapi.yaml) añade `report_verification` como propiedad opcional de `EvaluationReport`, los esquemas `ReportEvalRates/Run/VerificationEval` y `cifra_omitida` en el enum; la ruta sigue referenciando `EvaluationReport`, que ahora lo contiene, y `assert_matches(body, "EvaluationReport")` sigue pasando (sin `additionalProperties: false`). [data-model.md](docs/data-model.md) actualizado. Detalle cosmético: el código llama a la respuesta `EvaluationOut` y el path `EvaluationReport`.
- **Reintento API.** `needs_api_retry` solo acepta `muse_no_disponible`; ese camino siempre llega sin intentos (excepción), así que `mark_retry` no pierde costo; un solo reintento en serie, termina.
- **Prompts intactos** (sin diff en `prompts.py`/`schemas.py`; el versionado del fallback no se rompe). **Sin estaciones ni secretos**: `git grep -Ef .forbidden-terms` vacío; `_result` excluye `lat/lon`; `.env.example` sin secretos. **TDD**: pares `test()`→`fix()/feat()` en español y líneas en el README.

## Mejoras (no bugs)

- Falsos negativos de alcance, casi todos declarados: números en palabras (`medio metro`, consagrado como `[]` en tests), exageraciones sin cifra (`casas arrasadas`, en Limitaciones del README), `5 m2`/`5 cm3`, `-5 metros`. `_covers` acepta cualquier unidad equivalente, pero la unidad equivocada cae igual en `cifra_no_coincide`: sin agujero.
- `TEXTS_FROM` publicado dice "LLM (opencode)" mientras README/ADR precisan "Muse Spark 1.3 vía opencode": pierde precisión en `GET /evaluation`.
- `REPORT_EVAL_FILE` es campo requerido aunque el feature es opcional; sigue la convención del repo, solo anotarlo.
- Los `reports/*.jsonl`, `*.summary.json` y `report_eval.json` versionados tensionan la regla 9; la nota del README solo justifica la spec. Decisión consciente, pero la justificación no cubre estos artefactos.
- Falta `docs/reviews/TASK-036.md` (DoD §8 / regla 13): la rama toca núcleo y contrato; esta revisión debería guardarse ahí.
- NFR-2 incumplido (p95 ≈ 81 s) ya declarado honestamente en PRD/ADR con mitigación (`202` + demo grabada); limitación de v1, no defecto de la rama.

## Qué se hizo

| # | Hallazgo | Decisión | Commit |
|---|----------|----------|--------|
| B1 | `GET /evaluation` da 500 con un `REPORT_EVAL_FILE` ilegible | Corregido (TDD): `OSError` → `null` | test en rojo y fix de esta revisión |
| B2 | `publish_summary --run` sin validar | Corregido (TDD): `parse_run` | ídem |
| M | `TEXTS_FROM` impreciso | Corregido: nombra Muse Spark 1.3 Contributor vía opencode (D-07) | ídem |
| M | Regla 9 sin justificar para `reports/` | Nota ampliada en `eval-harness/README.md` | este commit |
| M | Falta `docs/reviews/TASK-036.md` | Este archivo | este commit |
| M | Números en palabras, `5 m2`, `-5 metros`, `REPORT_EVAL_FILE` requerido, nombre `EvaluationOut` | Anotado, sin cambio (limitaciones declaradas en el README) | — |
