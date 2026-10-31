# Revisión de Muse Code — día 2 (2026-10-31)

> **Comando:** `muse exec --model muse-spark-1.3 --contributor-mode off --effort medium "Revisa src/climapp/verification/, src/climapp/data/groups.py, src/climapp/data/outages.py, src/climapp/data/cleaning.py, src/climapp/api/ y sus tests contra CLAUDE.md, docs/dod.md, docs/adr/ADR-002-muse-spark-verificacion.md y docs/openapi.yaml. Busca errores de lógica en la compuerta (orden de motivos, reintentos, juez), en la confianza (que duplicar estaciones no la infle) y en el fallback. No edites nada."`
> **Versión:** Muse Code 1.4.14. **Commit revisado:** `ec94291` (TASK-002 mínima, 011, 012, 013, 014 y 022 cerradas).
> **Entorno:** copia de `git ls-files` (sin `data/`, `.env` ni `.forbidden-terms`). El workspace no era de confianza: Muse leyó `CLAUDE.md` como documento, no como reglas propias.
> **Solo lectura:** `diff -rq` contra una copia previa (excluyendo cachés) sin diferencias.

## Salida (rutas absolutas de la copia reemplazadas por rutas del repo)

Revisión en solo lectura, sin cambios. Comparé el código con [ADR-002](`docs/adr/ADR-002-muse-spark-verificacion.md`), [openapi.yaml](`docs/openapi.yaml`), [DoD](`docs/dod.md`) y [CLAUDE.md](`CLAUDE.md`).

## Compuerta: orden, reintentos y juez — sin errores de lógica

- El orden de [checks.py](`src/climapp/verification/checks.py:102) (`incompleta → vacía → esquema → cifra → herramienta`) coincide con ADR-002 §3. El test `test_all_failing_reasons_are_reported_in_adr_order` lo fija.
- El juez solo corre si las deterministas pasan ([gate.py](`src/climapp/verification/gate.py:97)`), como exige el ADR ("primero y gratis"). Test correspondiente en verde.
- Reintentos: bucle 1..max ([gate.py](`src/climapp/verification/gate.py:123)`), cada intento recibe los motivos del anterior ([gate.py](`src/climapp/verification/gate.py:136)`), y tras agotar pasa a `requiere_revision_humana`. `VERIFY_MAX_ATTEMPTS=3` en `.env.example`. Correcto.
- Dos notas menores, no bugs: los reintentos solo llevan los motivos del intento inmediato (el ADR dice "del anterior", en singular, así que es fiel); y `_judge` normaliza mayúsculas/espacios ([gate.py](`src/climapp/verification/gate.py:67)`), lo que acepta paráfrasis menores del juez aunque el prompt le pide copia literal. Lenidad consciente.

## Confianza: duplicar no infla — con una salvedad acotada

- Cada grupo aporta una sola fuente con `max()` ([confidence.py](`src/climapp/verification/confidence.py:107)), así que una copia dentro del mismo grupo no cambia el puntaje ni el conteo. El property test `test_duplicating_a_correlated_station_never_raises_confidence` lo demuestra, incluido el caso de la media que antes sí inflaba.
- Salvedad: las estaciones fuera del archivo de grupos se vuelven cada una su propia fuente (`loose`, [confidence.py](`src/climapp/verification/confidence.py:105)`). Duplicar una estación *no agrupada* con otro id sí sumaría fuente. Hoy no afecta porque `build_groups` lista todas las EST-x con días válidos, pero el archivo de grupos es el que sostiene la garantía.
- Terminología: `independent_sources=len(sources)` ([confidence.py](`src/climapp/verification/confidence.py:168)`) cuenta grupos + satélite + pronóstico (el test espera 5 para 3 grupos + 2). El [data-model](`docs/data-model.md:88) dice "número de grupos, no de estaciones". Es ambiguo en palabras, pero código, test y OpenAPI son coherentes entre sí.

## Fallback: el único hallazgo real está en los datos grabados

- El mecanismo es correcto: `RecordedMuseClient` marca `fallback=True`, la compuerta no se salta y `_any_fallback` propaga la marca ([muse.py](`src/climapp/verification/muse.py:207), [gate.py](`src/climapp/verification/gate.py:140)`). La API publica `explanation`/`explanation_fallback` según contrato.
- El problema: en [muse_fallback.json](`config/muse_fallback.json:44) los tres veredictos del juez para `explicar` dicen `supported=false`. Con ese archivo, un `explain_forecast` con `DEMO_FALLBACK=1` agota 3 intentos en `afirmacion_sin_evidencia` y devuelve `None`. La demo sigue respondiendo 200 con `explanation=null` (válido por contrato y DoD §12), pero sin texto de explicación. Los tests no lo detectan porque usan grabaciones sintéticas con `supported=true`.
- Efecto secundario a documentar: el juez estricto frente a evidencia serializada como JSON (claves como `probabilidad_pct`, [explain.py](`src/climapp/verification/explain.py:63)`)) parece rechazar explicaciones legítimas. Conviene una pareja `explicar`+`juez` grabada que sí pase, o dejar constancia de que la demo muestra `null`.

## Datos y API: coherentes, con un hueco de alcance conocido

- [groups.py](`src/climapp/data/groups.py:144) usa `TRAIN_START..TEST_END`, tal como decidió el equipo el 2026-10-31. [outages.py](`src/climapp/data/outages.py:87) invalida y anula `precip_mm`; los grupos excluyen esos días. Sin contradicción.
- [cleaning.py](`src/climapp/data/cleaning.py:119) solo marca `SUSPECT` y conserva la lluvia; la exclusión de `suspect_mm` del total ocurre aguas abajo según el modelo de datos. Coherente.
- `GET /forecast` y `GET /evaluation` cumplen el contrato (variantes, 422/503, `stale`, aviso, `explanation=null` si la compuerta falla). Pero `POST /reports`, `GET /reports` y `GET /reports/{id}` siguen sin implementarse en [main.py](`src/climapp/api/main.py:188)`; solo hay `/forecast` y `/evaluation`. Ya estaba registrado en `docs/reviews/dia-1b.md`. No es un error de lógica de la compuerta, pero la verificación de reportes aún no tiene quien la invoque de extremo a extremo.

Nada fue editado.

## Atención
| # | Hallazgo | Decisión |
|---|----------|----------|
| 1 | Compuerta: orden, reintentos y juez sin errores; juez con normalización de mayúsculas y espacios | Sin cambios: la normalización es intencional (la afirmación debe ser la misma, no una paráfrasis) |
| 2 | Confianza: una estación fuera del archivo de grupos cuenta como su propia fuente | Aceptado como límite conocido: `climapp-groups` lista todas las `EST-x` con días válidos, así que hoy no ocurre. La garantía depende de regenerar los grupos cuando entre una estación nueva |
| 3 | `independent_sources` cuenta grupos más satélite y pronóstico, y el modelo de datos decía "número de grupos" | **Atendido**: se aclaró `docs/data-model.md` |
| 4 | Las grabaciones de la explicación de E1 tienen `supported=false`: con `DEMO_FALLBACK=1` la demo muestra `explanation=null` | **Pendiente de decisión del equipo.** Es el resultado real de la única prueba contra Meta. Causa probable: el juez recibe las cifras con claves (`probabilidad_pct`) sin su significado ("probabilidad de 20 mm o más mañana en la cuenca"). Para corregirlo hay que enriquecer la evidencia del juez (con TDD) y hacer una segunda corrida real, que requiere aprobación |
| 5 | `POST /reports`, `GET /reports` y `GET /reports/{id}` sin implementar | Esperado: TASK-016 (lunes) |
