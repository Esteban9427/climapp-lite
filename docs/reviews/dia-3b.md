# Revisión de Muse Code — día 3b (2026-11-01)

> **Comando:** `muse exec --model muse-spark-1.3 --contributor-mode off --effort medium "Revisa en solo lectura lo construido hoy después de la revisión del día 3: (1) src/climapp/data/level.py (drop_single_spikes, NIVEL_MAX_STEP_M) y tests/data/test_level.py; (2) src/climapp/verification/muse.py (RecordedMuseClient reproduce en orden y de forma cíclica las grabaciones repetidas) y tests/verification/test_muse.py; (3) el cambio de la demo: .env.example, config/demo_reports.json, config/muse_fallback.json y tests/test_e2e_demo.py; (4) docs/PRD.md, ADR-001, ADR-002, ADR-004, docs/backlog.md y README. [...] No edites nada."` (pedido completo en la sesión).
> **Versión:** Muse Code 1.4.14. **Commit revisado:** `09eb177`.
> **Entorno:** copia de `git ls-files` (sin `data/`, `.env` ni `.forbidden-terms`). El workspace no era de confianza: Muse leyó `CLAUDE.md` como documento, no como reglas propias. Sin git en la copia y sin poder correr `uv`: no verificó historial, suite, cobertura ni linters.
> **Solo lectura:** `diff -rq` contra una copia de control (excluyendo cachés), sin diferencias.

## Cómo se atendió
| Hallazgo | Decisión | Evidencia |
|----------|----------|-----------|
| El filtro de picos borra una lectura buena entre dos picos (`[0,5, 13,0, 0,51, 13,1, 0,5]`) | **Corregido** | Cada lectura se compara con la última conservada. `410df60` (rojo) → `4f61038`. En la serie real siguen 4 picos y `level_daily.csv` queda idéntico |
| Un pico de dos lecturas pasa el filtro | Se mantiene, con test | Es lo declarado ("una sola lectura"); test `test_a_two_reading_spike_is_kept_by_design`. Se suma a la pregunta para JM (PRD SP-18) |
| Un pico en la última lectura del archivo inflaría la subida de ese día | Se mantiene | Sin vecino siguiente no se ve el regreso; la serie real termina el 2026-10-22 sin pico |
| El contador del fallback es global: dos verificaciones simultáneas del mismo texto se roban grabaciones | Se mantiene, documentado | La demo es de un solo usuario y secuencial; con dos a la vez el orden puede cambiar, pero nunca recibe la respuesta de otro pedido (solo de la misma entrada exacta). Queda en ADR-002 §5 |
| El ciclo reutiliza la grabación 1 en un 4.º intento | Se mantiene | La compuerta limita a 3 intentos (`VERIFY_MAX_ATTEMPTS`); declarado en el docstring y fijado por test |
| `DEMO_FORECASTS` replica cifras de los artefactos publicados: un reentrenamiento las desincroniza | Se mantiene | Igual que E1; no se reentrena (ADR-001 §1). Si se reentrena, se regraba |
| Las 8 grabaciones anteriores intactas: no verificable sin git | **Verificado fuera de la copia** | `git diff` del fallback en `c98903a`: solo inserciones; comparación de las 8 primeras entradas contra la versión anterior: idénticas |
| Cifras del nivel y de E3 sin prueba automática | Se mantiene | Por la regla 9 los tests usan datos sintéticos; las cifras salen del inventario del 2026-11-01 (scripts de solo lectura fuera del repo) |
| `.env.example` versiona una ruta de la entrega del 2026-10-29 con las iniciales de una persona | **Corregido** (decisión de JE) | `STATION_EXPORTS` usa rutas genéricas (`raw/<entrega>/estaciones.xls` y `.csv`); las reales quedan solo en `.env` |

## Incidente: nombre de una estación en el historial público (2026-11-01)
- **Qué pasó:** el commit `eee52a0` (docs de E3) citó en `docs/PRD.md`, 3 veces, el nombre del archivo de eventos de nivel de la entrega de JM. Ese nombre incluye el de una estación (regla 10, ADR-004). El commit se subió al repositorio público.
- **Por qué no se detuvo:** el chequeo previo (`gitleaks` más la búsqueda de `.forbidden-terms` en lo preparado) sí lo detectó (`forbidden-terms = 3`), pero se corrió como `bash leaks.sh | tail -4 && git commit ...`. El código de salida de la tubería era el de `tail` (0), así que el commit y el push siguieron igual.
- **Arreglo:** `09eb177` reemplaza el nombre del archivo por una descripción; el árbol vuelve a dar 0. Desde entonces el chequeo se corre con `set -o pipefail` y sin `tail`, y un fallo detiene el commit. También se revisaron los mensajes de commit y los archivos de los commits de ese día: el término solo aparece en `eee52a0`.
- **Decisión de JE: no se reescribe el historial ni se hace force-push.** Reescribirlo cambiaría los hashes de los commits del evento, que son la evidencia de lo construido durante el evento (R10). D-03 está cerrado (la CVC autorizó el uso de los datos el 2026-10-31) y la fuente CVC ya es pública. El nombre queda en `eee52a0` como incidente documentado.

## Salida (rutas absolutas de la copia reemplazadas por rutas del repo; sin las líneas de arranque del CLI)

Revisión en solo lectura terminada. No edité nada. No pude correr `pytest`, `ruff` ni `mypy` (la caché de `uv` es de solo lectura en este entorno), así que todo lo verificado es por lectura de código; donde ejecuté algo lo marco.

## Veredicto

Lo construido hoy está en buen estado y es coherente con `CLAUDE.md`, `dod.md` y `openapi.yaml`. Encontré un bug real en el filtro de picos (borra lecturas buenas en un patrón concreto), un problema de concurrencia en el fallback cíclico, y varios puntos menores. Ninguna afirmación de cifras que verifiqué está mal sumada.

## 1. Filtro de picos ([level.py](src/climapp/data/level.py))

El predicado `_is_spike` es correcto para picos aislados de una lectura, en ambos sentidos. El borde es estricto (`>`), así que un salto exactamente igual al límite se conserva. Hay test que lo fija.

Bug: `drop_single_spikes` evalúa en una sola pasada contra los vecinos originales. Si dos picos de una lectura están separados por una sola lectura buena, la buena también cae. Repliqué el predicado fuera del repo (no pude importar el módulo: falta `openpyxl` fuera de `uv`) y obtuve:

- `[0.5, 13.0, 0.51, 13.1, 0.5]` → `[0.5, 0.5]`. El `0.51` bueno se descarta.
- Consecuencia: con picos alternos, el filtro sobre-borra. En la serie real hay solo 4 picos aislados, así que el impacto hoy es nulo. Pero conviene un test con ese patrón y, si se quiere robustez, una pasada iterativa.

Por diseño (documentado en el docstring, sin error):

- Los picos de dos lecturas `[0.5, 13.0, 13.1, 0.5]` se conservan. Es lo declarado ("una sola lectura"), pero un sensor atascado dos lecturas pasa el filtro.
- Los extremos siempre se conservan. Un pico en la última lectura del archivo inflaría `rise_24h_max_m` de ese día. Aceptado conscientemente; lo anoto por el efecto.
- Duplicados: se queda la primera en orden de entrada y luego ordena. Test existente lo cubre.
- Ventana de 24 h cerrada (`<` al expulsar) y medianoche: correctas, con tests.

## 2. Fallback cíclico ([muse.py](src/climapp/verification/muse.py))

El fallo cerrado se mantiene: la rama cíclica solo se alcanza dentro de la lista exacta (misma tarea, versión de prompt y hash). Un pedido sin grabación exacta sigue lanzando `MissingRecordingError`. El docstring ya no promete de más.

Dos observaciones:

- Concurrencia: el contador `_served` es global por `(tarea, versión, hash)` y el `Lock` solo protege el incremento, no la secuencia de una verificación. Dos verificaciones concurrentes del mismo texto se roban grabaciones: la segunda recibe la grabación del intento 2 en su intento 1. Los tests no lo detectan porque cada fixture crea un cliente nuevo y todo corre secuencial. En la demo secuencial no hay problema; con dos usuarios a la vez sí. Sugiero documentar uso monohilo de demo o un cursor por verificación.
- El ciclo envuelve: el intento 4 reutiliza la grabación 1 (el test lo fija: `rechaza, acepta, rechaza, acepta`). La compuerta hoy limita a 3 intentos, así que es inocuo. Pero enmascara un sobre-reintento en vez de fallar cerrado. Está declarado en el docstring ("vuelve a empezar"), así que es decisión, no accidente.

## 3. Demo

- [`.env.example`](.env.example): `DEMO_REPLAY_DATE=2026-10-01` y `DEMO_REPORT_TIME=2026-10-02T16:30:00-05:00` coinciden con [test_e2e_demo.py](tests/test_e2e_demo.py). Tipos coherentes con `config.py` (`date | None`, `datetime`).
- [`muse_fallback.json`](config/muse_fallback.json): 25 grabaciones = 8 + 17, y las 17 nuevas van al final. No pude verificar que las 8 primeras estén intactas: no hay git en esta copia.
- Los tests de la demo no dependen de datos reales: escriben CSV sintéticos, bloquean red por socket y leen el fallback versionado. Correcto.
- Fragilidad conocida y documentada: `DEMO_FORECASTS` hardcodea probabilidades, acumulado y `model_version` como réplicas de los artefactos publicados. Un reentrenamiento las desincroniza sin que ningún test lo detecte desde el modelo. Aceptable para demo, pero es deuda anotada.
- Asimetría menor: el caso E3 trae ambas variantes y E1 solo `historica` en `E1_FORECASTS`.

## 4. Docs y cifras

- Totales de ADR-002 corrida 5: los recomputé a mano y cuadran (38 llamadas, 10 964 / 46 518 tokens, US$0,2114).
- "5 de 13" (`operativa`) y "4 de 13" (`historica`): consistentes entre [PRD.md](docs/PRD.md), ADR-001 y README. La limitación "avisa el día después" se comunica con honestidad, incluyendo fallo y falsa alarma de E3.
- ADR-001 §Consecuencias ↔ PRD antes/después: coinciden (umbral 0,114→0,132, POD 0,68→0,29, E1 0,146→0,132 / 0,114→0,149).
- SP-5 cerrado en E3 con E1 conservada como falsa alarma: coherente en PRD, backlog y tests. SP-18 deja preguntas abiertas a JM y el código efectivamente no toca negativos ni el piso de 0,35 m. Coherente.
- No verificables sin `DATA_DIR`: "4 picos de hasta 13,68 m", "los días de E3 no cambian", valores de nivel de E3 (0,68 m; 0,41→1,07) y "175,6 mm y +0,72 m". Descansan en el inventario manual, no en CI. Por regla 9 los fixtures son sintéticos, así que esto es esperado; solo anoto que README/PRD las presentan como hechos sin prueba automática que las fije.
- ADR-004 §5 y §8 coinciden con el código: filtro por `LEVEL_SERIES_ID`, definición de subida, duplicados-primero, sin criterio de día válido, nombre real del archivo solo en `.env`.

## Lenguaje, nombres y hardcode

- Lenguaje de alerta: limpio. La plantilla base dice "No es una alerta oficial" y el e2e lo exige. La sonda que hablaba de "alerta de creciente" se documenta como rechazada. Bien.
- Estaciones: solo `EST-x` en código, tests y docs. Un posible lunar: `.env.example` versiona la ruta `ExportJMN_Pance.csv`, con las iniciales de una persona en el nombre del archivo entregado. No es nombre de estación, pero es un identificador personal en el repo; no pude correr el `git grep` de `.forbidden-terms` para confirmar.
- Hardcode: además de las probabilidades de la demo, nada relevante. `LEVEL_SENSOR=NIVEL` es genérico y `LEVEL_EXPORTS` usa nombre descriptivo, como exige el ADR.
