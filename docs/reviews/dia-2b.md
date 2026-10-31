# Revisión de Muse Code — día 2b (2026-10-31, tarde)

> **Comando:** `muse exec --model muse-spark-1.3 --contributor-mode off --effort medium "Revisa en solo lectura lo construido hoy: src/climapp/api/ (reports.py, store.py, photos.py, forecast_routes.py, deps.py), src/climapp/verification/ (basin.py, evidence.py, reports.py, explain.py, prompts.py), src/climapp/web/ (views.py, map.py, templates/, static/app.js, static/map.js) y sus tests, contra CLAUDE.md, docs/dod.md, docs/adr/ADR-002-muse-spark-verificacion.md, docs/design.md y docs/openapi.yaml. Busca: fugas de privacidad (EXIF, texto del ciudadano, coordenadas sin redondear), XSS en plantillas o en el JSON embebido del mapa, inyección SQL, que la compuerta pueda saltarse, estados de diseño faltantes y discrepancias con el contrato. No edites nada."`
> **Versión:** Muse Code 1.4.14. **Commit revisado:** `11347bd` (TASK-016 a TASK-019 cerradas).
> **Entorno:** copia de `git ls-files` (sin `data/`, `.env` ni `.forbidden-terms`). El workspace no era de confianza: Muse leyó `CLAUDE.md` como documento, no como reglas propias.
> **Solo lectura:** `diff -rq` contra una copia previa (excluyendo cachés) sin diferencias.

## Salida (rutas absolutas de la copia reemplazadas por rutas del repo)

Revisión solo lectura. No edité nada.

# Veredicto

Sin fugas directas ni bypass de compuerta. 3 hallazgos menores: `claims` expone texto casi literal, `bindPopup` es XSS almacenado latente, y `/mapa` no tiene lista de respaldo.

# Privacidad

- EXIF bien: [photos.py](src/climapp/api/photos.py:39) reconstruye solo píxeles y recodifica. Cubre JPEG y PNG.
- Tests lo prueban: [test_photos.py](tests/api/test_photos.py:23) y [test_reports_api.py](tests/api/test_reports_api.py:120).
- Coordenadas redondeadas en toda salida pública vía `ReportRecord.public()`: [schemas.py](src/climapp/api/schemas.py:66), llamado en [reports.py](src/climapp/api/reports.py:152), [views.py](src/climapp/web/views.py:76) y [map.py](src/climapp/web/map.py:74). `PUBLIC_COORD_DECIMALS=3` en `.env.example`. Test confirma `(1.512, -1.499)`.
- Texto y foto nunca en `Report` público. `public()` excluye ambos. Plantillas no renderizan `text`. Fotos se guardan en disco pero no hay ruta que las sirva. `main.py` solo monta `/static`.
- Matiz: `structured.claims` sí se publica por contrato en `GET /reports`. Son frases casi literales del ciudadano (ej. `CLAIMS` en tests). El docstring dice "nunca se publica el texto", pero el contrato exige `claims`. Es divulgación residual prevista por `openapi.yaml`, no fuga accidental.

# XSS

- Plantillas usan `{{ }}` con autoescape. No hay `|safe`.
- JSON del mapa seguro: [mapa.html](src/climapp/web/templates/mapa.html:22) usa `|tojson` en `script application/json`, y [map.js](src/climapp/web/static/map.js:4) lee con `JSON.parse(textContent)`.
- Latente: [map.js](src/climapp/web/static/map.js:13) pasa `m.label` a `bindPopup()`, que interpreta HTML. Hoy es seguro porque [map.py](src/climapp/web/map.py:57) arma el label solo con enums (`event_type`, `intensity` en [schemas.py](src/climapp/verification/schemas.py:15)) más un número. Si un enum se amplía o entra texto del LLM, se vuelve XSS almacenado.
- `map.js:10` concatena `attribution_url` en HTML. Es valor de operador, no de usuario. Riesgo bajo.
- `href="{{ official_url }}"` en [base.html](src/climapp/web/templates/base.html:15) escapa comillas pero no bloquea `javascript:`. Solo configurable por operador.

# SQL

- Seguro. [store.py](src/climapp/api/store.py:44) usa parámetros `?` en `INSERT`, `UPDATE`, `SELECT`. El `WHERE` se arma solo con cláusulas fijas ([store.py](src/climapp/api/store.py:68)). `limit` va como parámetro.

# Compuerta

- No saltable. [reports.py](src/climapp/api/reports.py:156) siempre encola `_verify_in_background` → `ReportVerifier.verify()` → `run_gate`. Web usa el mismo `post_report` ([views.py](src/climapp/web/views.py:110)).
- Fuera de cuenca se rechaza sin LLM ([reports.py](src/climapp/api/reports.py:149)). Es rechazo determinista, no bypass. Test exige `muse.requests == []`.
- Foto sin texto va a `requiere_revision_humana` sin LLM ([reports.py](src/climapp/verification/reports.py:46)). Correcto según ADR-002.
- Pronóstico nunca muestra texto sin verificar: [_explained](src/climapp/api/forecast_routes.py:83) devuelve `explanation=None` si falla. Fallback pasa por la misma compuerta y marca `fallback=true` ([gate.py](src/climapp/verification/gate.py:140)).
- Orden deterministas → juez se cumple ([gate.py](src/climapp/verification/gate.py:95)). `max_attempts` de configuración.
- Nota: reintentos solo reenvían mensaje original más último feedback ([gate.py](src/climapp/verification/gate.py:136)). Cumple "recibe los motivos del anterior", pero pierde historial largo.

# Diseño y contrato

Faltantes contra [design.md](docs/design.md:96):

- Lista sin estados "Cargando…" ni "No se pudo cargar la lista". Se renderiza en servidor. Fallo de BD sería 500, no el estado de error diseñado.
- `/mapa` sin lista de respaldo. Diseño exige que si el mapa base falla, la lista siga accesible. [mapa.html](src/climapp/web/templates/mapa.html:8) solo tiene leyenda y `#map`.
- `reject_reason=entrada_invalida` inalcanzable. El contrato lo permite y [report_status.html](src/climapp/web/templates/partials/report_status.html:21) lo renderiza, pero el código nunca guarda `rechazado/entrada_invalida`. Inválidos son 422. La compuerta solo devuelve `verificado` o `requiere_revision_humana`.

Contrato `openapi.yaml`: alineado en lo revisado. `POST /reports` 202/422/503, `GET /reports/{id}` 200/404, `limit` 1–500 default 100, `historica` sin `replay_date` → 422, `from`/`to` con alias correctos. Tests de contrato con `assert_matches` cubren `Report` y `Error`. Diferencia menor: web acepta `text=""` y lo convierte a `None` ([views.py](src/climapp/web/views.py:118)), mientras API exige `min_length=1`. Comportamiento final igual (422 sin texto ni foto).


## Atención
| # | Hallazgo | Decisión |
|---|----------|----------|
| 1 | `structured.claims` publica frases casi literales del ciudadano | **Pendiente de decisión del equipo.** El contrato (`Report.structured`) exige publicar `claims`. Opciones: dejarlo (las afirmaciones son el registro verificado) o publicarlas solo en la vista de detalle. Hoy la web muestra solo el tipo, la intensidad y la confianza, no las `claims` |
| 2 | `bindPopup(m.label)` interpreta HTML (XSS latente) | **Atendido** con test: el popup se arma con `textContent` |
| 3 | `href` de los enlaces de configuración acepta `javascript:` | **Atendido** con test: `OFFICIAL_CHANNELS_URL`, `IDEAM_ALERTS_URL` y `MAP_ATTRIBUTION_URL` solo aceptan http(s) |
| 4 | `/mapa` sin la lista de respaldo que pide el diseño | **Atendido** con test: lista `#map-list` con los mismos marcadores en texto |
| 5 | La lista no tiene los estados "Cargando" ni "No se pudo cargar" | Aceptado: la lista se renderiza en el servidor, así que nunca se ve "cargando". Un fallo de la base es un 500 y el aviso se mantiene. Se revisa si la lista pasa a cargarse con HTMX |
| 6 | `rechazado/entrada_invalida` es inalcanzable | Aceptado: la entrada inválida es 422 antes de guardar (contrato). El valor queda en el enum para una moderación futura |
| 7 | Los reintentos solo llevan los motivos del intento anterior | Sin cambios: es lo que dice ADR-002 §3 |
| 8 | La web convierte `text=""` en `None` y la API exige `min_length=1` | Sin cambios: el resultado es el mismo (422 sin texto ni foto). El campo de texto vacío es normal en un formulario |

**Revisión manual a 360 px (DoD de TASK-017):** capturas con Chrome headless de `/`, `/?replay_date=2024-12-31` y `/mapa`. Una columna, sin scroll horizontal, contraste y estados según `docs/design.md`. El aviso fijo ocupaba ~190 px y se acortó a ~108 px (`fix(task-017)`).
