# Gate 4 — QA (forge-qa)

> **Veredicto:** APROBADO · **Fecha:** 2026-11-02 · **Commit verificado:** `99ac8c8` (`main`, igual a origin/main) · **Agente:** `forge-qa` con contexto limpio, sin editar `src/`.
>
> Reporte guardado tal cual. Solo se quitaron la ruta local del respaldo de la base y la ruta del notebook de datos crudos.

FORGE:QA> Gate 4: ClimApp Lite en `main` @ `99ac8c8` (igual a origin/main, árbol limpio antes y después)

## Resultado: APROBADO

Pasan los 6 criterios. No hay bugs CRITICAL ni HIGH, así que no hay fixes que proponer. No modifiqué ningún archivo versionado y no escribí `docs/qa-report.md`; la evidencia va en este informe. Hay 3 observaciones que no bloquean (al final).

Antes, dos datos de proceso:
- **`docs/handoff-gate3.md` no existe.** Trabajé solo con los artefactos en disco: `docs/dod.md`, `docs/sprints/sprint-1.md` y `core-paths.txt`.
- **`forge gate check 4 --path …` no se puede usar aquí.** Responde: "faltan G1, G2, G3 aprobados (state.json o CLAUDE.md)". El proyecto no tiene estado de FORGE, así que la verificación se hizo con los comandos reales que siguen.

## 1. Cobertura del núcleo (≥ 85 %): PASA
- `uv run pytest -q --cov=climapp --cov-report=term-missing` da **693 passed** en 45 s y **99 % global** (2953 sentencias, 33 sin cubrir).
- `uv run coverage report --include='src/climapp/forecast/*,src/climapp/verification/*'` da **99 % en el núcleo** (1273 sentencias, 6 sin cubrir). Los únicos módulos por debajo de 100 % son `forecast/model.py` (93 %), `forecast/cli.py` (97 %) y `forecast/dataset.py` (97 %).
- Además: `ruff check .` dice "All checks passed!", `ruff format --check .` dice "143 files already formatted" y `mypy src` dice "Success: no issues found in 56 source files".

## 2. SAST: PASA
- **bandit** no está en el entorno de uv; lo corrí con `uvx bandit -r src/ -ll`. Revisó 5045 líneas y encontró **High 0, Medium 1 (Confidence Low), 0 `#nosec`**.
  - El único hallazgo es B608 en `src/climapp/api/store.py:95`, y es un **falso positivo**. El `WHERE` se arma solo con cláusulas fijas (`"status=?"`, `"local_day>=?"`, `"local_day<=?"`), y todos los valores, incluido `LIMIT ?`, van como parámetros. El `# noqa: S608` tiene su justificación en la línea 94.
- **semgrep**: `uvx semgrep scan --config p/python --config p/secrets --metrics=off --json src/` revisó 67 archivos con **0 resultados y 0 errores**.
- **pip-audit** (extra): `uv export --no-dev` y luego `uvx pip-audit -r … --disable-pip --no-deps` dan "No known vulnerabilities found".

## 3. Secretos en todo el historial: PASA
- `gitleaks git --log-opts="--all" --redact -v .` (gitleaks 8.30.1) revisó **185 commits de 185**, unos 1,62 MB: **"no leaks found"**, exit 0.
- Como contraste, `gitleaks dir --redact .` sobre el disco encuentra 3 hallazgos, todos en archivos ignorados por git y nunca versionados:
  - `.env` líneas 2 y 13 (generic-api-key y jwt). Lo ignora `.gitignore:12` y `git log --all -- .env` está vacío.
  - Notebook entregado por el equipo (jwt). Lo ignora `.gitignore:2 /data/` y `git log --all -- data/` está vacío. Ver la observación O-1.

## 4. 0 bugs CRITICAL/HIGH abiertos: PASA
- No hay bugs CRITICAL/HIGH en `docs/` (busqué `BUG-|CRITICAL|HIGH` en el backlog, el sprint y las reviews). `gh issue list --state open` no devuelve issues.
- Las pruebas que hice como atacante y de errores, contra el servidor en vivo, respondieron todas según el contrato:

| Prueba | Resultado |
|---|---|
| UUID inexistente | 404 `reporte_no_encontrado` |
| id que no es UUID | 422 |
| POST sin texto ni foto | 422 "envía un texto o una foto" |
| lat=999 | 422 |
| Punto fuera de la cuenca | 202 `rechazado` / `fuera_de_cuenca` |
| `limit=0` | 422 |
| `status=bogus` | 422 |
| `variant=historica` sin `replay_date` | 422 `variante_no_disponible` |
| `replay_date=1990-01-01` | 503 `sin_pronostico` |
| El mismo texto reenviado | `duplicate: true` |

- Con `META_API_BASE_URL=http://127.0.0.1:9/v1`, un reporte sin grabación queda en el log como `report.no_recording`, que es un fallo cerrado. No se hizo ninguna llamada a la red.

## 5. `.forbidden-terms`: PASA en HEAD; un incidente histórico ya aceptado
- El archivo tiene 5 patrones. `git grep -niEf .forbidden-terms` da **0 resultados, exit 1**, que es lo que mide la DoD §7.
- En todo el historial (`git grep -cniEf .forbidden-terms $(git rev-list --all)`) hay una sola coincidencia: `eee52a0:docs/PRD.md:3`. Son 3 líneas con el mismo término; el fix es `09eb177`.
- Ese commit ya está en origin/main y **el repo es PUBLIC** (`gh repo view`).
- **No lo abro como bug:** el incidente está documentado en `docs/reviews/dia-3b.md:21-25`, donde JE decidió no reescribir el historial porque los hashes son la evidencia R10, D-03 está cerrado y la fuente es pública. Lo dejo como riesgo aceptado. Si el operador quiere cambiar esa decisión, es suya.

## 6. Demo de punta a punta con DEMO_FALLBACK=1: PASA
Para que cualquier llamada a la red fallara, levanté el servidor con `META_API_BASE_URL=http://127.0.0.1:9/v1` y `EARTHDATA_TOKEN=invalid`.
- **Reset:** `DEMO_FALLBACK=1 uv run climapp-demo-reset --yes` da `demo_reset.done removed=0` en JSON, exit 0, y `select count(*) from reports` da 0.
- **Servidor:** `DEMO_FALLBACK=1 … uv run uvicorn climapp.api.main:app --port 8765`.
- **API:**
  - `GET /forecast?replay_date=2026-10-01` da 200 con target 2026-10-02, prob 0,149, risk `elevado`, `replay: true`, variante `operativa`, `explanation_fallback: true` y una explicación en es-CO que trae el aviso "no es oficial".
  - `GET /evaluation` da 200.
  - `GET /forecast` sin replay da 200 con `stale: true` y explicación null (no hay grabación; falla cerrado).
- **Los 3 reportes de `config/demo_reports.json`** (`POST /reports` da 202 a cada uno) terminan exactamente como dice `docs/PRD.md:159`:

| Reporte | Estado | Confianza | Fuentes |
|---|---|---|---|
| Verdadero | `verificado` | 1,0 | 5 (EST-A, EST-B+EST-C, IMERG_E, pronóstico, nivel) |
| Exagerado | `requiere_revision_humana` | — | — |
| Falso | `verificado` | 0,0 | 4, todas en desacuerdo |

  Los tres llevan `fallback: true`.
- **UI:**
  - `GET /` da 200 con "No es una alerta oficial".
  - `GET /?replay_date=2026-10-01` da 200.
  - `GET /mapa?replay_date=2026-10-01` da 200 con **2 marcadores**: el verdadero y el falso, igual que `tests/test_e2e_demo.py:281`.
  - `GET /web/reports/{id}/estado` da 200 con "Coincide con los datos".
  - `POST /web/reports` (HTMX) da 200.
  - Los 7 archivos estáticos (css, js, htmx, leaflet) dan 200.
- **Limpieza:** detuve el servidor y corrí `climapp-demo-reset --yes` otra vez (`removed=5`), así que la base quedó vacía como estaba. `git status` sigue limpio. Se guardó un respaldo previo de la base fuera del repo.

## Observaciones (no bloquean, no apliqué nada)
- **O-1 (MEDIUM, operativo, fuera del repo):** el notebook entregado por el equipo trae un JWT, que parece un token de Earthdata. No está en git, pero conviene avisar al equipo que lo entregó y rotarlo si es el token real.
- **BUG-001 (LOW, va al backlog post-hackathon por el congelamiento de alcance):**
  - Pasos: levantar la API y mirar sus logs.
  - Esperado: JSON, según CLAUDE.md regla 4 y la línea 55 del README ("los logs de módulo vuelven a salir en JSON").
  - Actual: la API emite logs con el formato de consola de structlog (`2026-11-02 20:17:03 [warning ] explain.muse_error …`).
  - Causa raíz: `src/climapp/api/main.py` importa `get_logger` pero nunca llama a `configure_logging()`; solo lo hacen las CLI.
  - Fix propuesto, para PROGRAMMER con TDD: llamar a `configure_logging()` al crear la app (factory o lifespan).
- **O-2 (LOW, proceso):** falta `docs/handoff-gate3.md` y el proyecto no tiene estado de FORGE, por eso `forge gate check 4` no se puede usar.

## Nodo KG propuesto (no lo escribí en `docs/kg-proposals.md`)
`{"type":"Lesson","phase":"qa","title":"El logging JSON se configura en cada punto de entrada, también en la app ASGI","body":"configure_logging solo se llamaba en las CLI; uvicorn emitía logs de consola. Agregar un test que capture stdout de la app y valide JSON."}`

Ruta del proyecto: /home/juanestebangallego/projects/climapp-lite
