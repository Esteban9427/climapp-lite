# ClimApp Lite

ClimApp Lite publica cada día la probabilidad de que mañana caiga lluvia de 20 mm o más en la cuenca del río Pance (Cali, Colombia), junto con un indicador de lluvia acumulada en 3 días como señal de riesgo de derrumbe. Está pensada para el ciudadano o turista que decide si va al río. Quienes están en la zona pueden confirmar lo que ven con texto o foto, como un "Waze del clima". Muse Spark estructura cada reporte y explica el pronóstico en lenguaje claro, y la confianza de cada confirmación la calcula código verificable, no el modelo.

## Team
- **Juan Manuel Nogales** — idea, domain expertise (hydroclimate monitoring), station data and narration.
- **Juan Esteban Gallego** — engineering, ML pipeline, verification gate and evaluation.

## How it was built
Product AI: Muse Spark 1.3 (Meta Model API) structures, judges and explains — on the critical path. Development: Claude Code as coding assistant under a TDD/gates workflow (FORGE); Muse Spark also did read-only code reviews and generated the simulated test reports.

> **⚠️ No es una alerta oficial.** ClimApp Lite es un proyecto experimental. Ante cualquier riesgo, sigue las indicaciones de los organismos oficiales de gestión del riesgo y de meteorología.

## Tema
**Build for Your World**: aplicamos los modelos de Meta al dominio hidroclimático que conocemos, en una cuenca concreta.

## Limitación conocida
El modelo tiende a avisar **el día después** de que empieza la lluvia: en los 13 eventos de nivel del río del periodo de prueba (2023-2026), acierta el primer día en 5 de 13. Por eso ClimApp Lite es un **pronóstico informativo, no una alerta**. Para alertas, consulte a la Gestión del Riesgo de Cali y al IDEAM. Detalle en `docs/PRD.md` (§Resultados del modelo y §Eventos documentados).

## Modelos de Meta usados
- **Muse Spark**, vía Meta Model API: estructura los reportes ciudadanos y explica el pronóstico.

## Construido durante el evento (26 oct a 4 nov 2026)
Todo lo que está en este repositorio se construyó durante el evento. La lista se llena a medida que se cierra cada función:

- [x] 2026-10-29: repositorio, licencia y fuentes de datos con su licencia y autorización (`docs/data-sources.md`).
- [x] 2026-10-29: especificación: PRD con IN/OUT, métricas y supuestos (`docs/PRD.md`), historias de usuario en Gherkin, ADR-001 a ADR-005, modelo de datos, contrato OpenAPI, backlog, alcance del MVP y DoD.
- [x] 2026-10-30: esqueleto del proyecto con uv (Python 3.12), pytest, ruff, mypy estricto, structlog y `Settings` que exige todas las claves de `.env.example` (TASK-001, TDD).
- [x] 2026-10-30: lectura de las exportaciones de estaciones (xls y csv con coma decimal ambigua) y limpieza del contador: reinicios, picos > `MAX_STEP_MM` y marca `suspect` de saltos aislados (TASK-003, TDD).
- [x] 2026-10-30: lector de CHIRPS diario por celda, sin las filas MIN, PROM y MAX ni las columnas resumen (TASK-005, TDD).
- [x] 2026-10-30: tabla diaria de estaciones por día local, con `valid` (≥ `MIN_READINGS`), `imputed=false` y `source_hash`, que une las dos exportaciones sin duplicar; se regenera con `uv run climapp-daily` (TASK-004, TDD).
- [x] 2026-10-30: corrección de huecos del contador: un paso sobre un hueco > `MAX_GAP_MIN` que cruza el día local no suma lluvia; `n_gap` en la tabla diaria (TDD).
- [x] 2026-10-30: objetivo de cuenca `basin_mean` con las estaciones válidas de cada día; sobre los datos reales da 10,2 % de días ≥ 20 mm, como ADR-001 (TASK-006, TDD).
- [x] 2026-10-30: líneas base (climatología ±15 días y persistencia) y métricas POD, FAR, CSI, Brier, AUC y calibración, sin días imputados (TASK-007, TDD).
- [x] 2026-10-30: variables con las estaciones disponibles cada día y CHIRPS, random forest calibrado y evaluado contra climatología y persistencia en 2023-2026, con test de fuga; `uv run climapp-train` escribe la evaluación y los pronósticos (TASK-008, TDD).
- [x] 2026-10-30: API `GET /forecast` (variante operativa en vivo e histórica en reproducción) y `GET /evaluation` sobre artefactos precalculados, con tests de contrato contra `openapi.yaml` y el aviso "no es alerta oficial" siempre presente (TASK-015, TDD).
- [x] 2026-10-31: correcciones de calidad de datos confirmadas por JM. Los saltos aislados del contador tras lecturas regulares se marcan `suspect` y no suman al total diario (SP-12); los días de periodos de falla conocidos quedan inválidos con un registro versionado (SP-13). Se regeneraron la tabla diaria y la evaluación (TASK-003 y TASK-004, TDD).
- [x] 2026-10-31: grupos de estaciones correlacionadas (r ≥ 0,8) sobre la tabla diaria, que cuentan como una sola fuente de evidencia (TASK-002 mínima, TDD).
- [x] 2026-10-31: cliente de Muse Spark con el SDK `openai` y el esfuerzo por tarea desde la configuración, más fallback de demo con respuestas reales grabadas y marcadas `fallback=true` (TASK-011, TDD).
- [x] 2026-10-31: compuerta de verificación: comprobaciones deterministas en el orden de ADR-002, juez con Muse Spark y hasta 3 intentos antes de `requiere_revision_humana` (TASK-012 y TASK-013, TDD).
- [x] 2026-10-31: confianza calculada por código, sin el LLM, con test de propiedades: duplicar una estación correlacionada no la sube (TASK-014, TDD).
- [x] 2026-10-31: explicación del pronóstico verificada: si una cifra no coincide con el modelo, o el juez la rechaza, `explanation=null` (TASK-022, TDD).
- [x] 2026-10-31: el juez recibe el significado de cada cifra; con eso la explicación de E1 se verifica con Muse Spark real y una explicación que habla de "alerta de creciente" se rechaza. El aviso nombra a la Gestión del Riesgo de Cali y al IDEAM. Los pesos de confianza quedan como SUPUESTO para JM (TASK-022, TASK-015 y TASK-014, TDD).
- [x] 2026-10-31: API de reportes ciudadanos. `POST /reports` responde 202 y verifica en segundo plano con la compuerta y la confianza; elimina EXIF y metadatos; rechaza fuera de la cuenca sin llamar al LLM. También `GET /reports` y `GET /reports/{id}`, con SQLite fuera de git (TASK-016, TDD).
- [x] 2026-10-31: web móvil (Jinja2 + HTMX) con el pronóstico, la explicación verificada, el formulario de reporte con estado en vivo y la lista de reportes verificados, según `docs/design.md`. Contraste AA verificado por test (TASK-017, TDD).
- [x] 2026-10-31: mapa mínimo con Leaflet y OpenStreetMap, con la atribución ODbL visible, los marcadores de los reportes verificados del día y en la leyenda el resultado del pronóstico (TASK-018, TDD).
- [x] 2026-10-31: privacidad de los reportes: la lista y el mapa solo muestran campos estructurados, sin id ni afirmaciones; las afirmaciones quedan en el detalle por UUID4. Una comprobación determinista rechaza teléfonos, correos y placas (TASK-016, TDD).
- [x] 2026-10-31: el fallback de la demo solo responde con coincidencia exacta (tarea, versión del prompt y hash de la entrada) y falla cerrado; un reporte nunca recibe la respuesta de otro. Se regrabaron E1 y 3 reportes de ejemplo con Muse Spark real (TASK-011, TDD).
- [x] 2026-10-31: reproducción de E1 de punta a punta con `DEMO_FALLBACK=1` y respuestas reales grabadas: pronóstico, explicación verificada, reporte verificado y mapa, con un test end-to-end que bloquea la red (TASK-019, TDD).
- [x] 2026-11-01: lector del nivel del río de la estación de la parte media y serie diaria con nivel mínimo, máximo y subida máxima en 24 h (`climapp-level`, TASK-038, TDD).
- [x] 2026-11-01: la subida de nivel del río es evidencia aparte en la confianza de los reportes que afirman una creciente; sin nivel ese día, la confianza no cambia (TASK-039, TDD).
- [x] 2026-11-01: el nivel descarta los picos de una sola lectura que saltan y regresan más de `NIVEL_MAX_STEP_M` (SUPUESTO 1,0 m); en los datos reales quita 4 picos de hasta 13,68 m y los días de la demo no cambian (TASK-038, TDD).
- [x] 2026-11-01: la demo pasa al evento del 2026-09-30: reproducción de la emisión 2026-10-01 (objetivo 2026-10-02, acierto) con 3 reportes de ejemplo marcados como simulados y regrabados con Muse Spark real; E1 queda como caso de falsa alarma. El fallback reproduce en orden las grabaciones repetidas (TASK-019 y TASK-011, TDD).
- [x] 2026-11-01: la web muestra, para cada reporte verificado, si los datos lo respaldan: "Coincide con los datos", "Coincidencia parcial" o "No coincide con los datos" (umbrales 0,7 y 0,3, SUPUESTO), en el estado, la lista y el mapa; el contrato de la API no cambia (TASK-017, TDD).
- [x] 2026-11-01: en una reproducción, el mapa muestra por defecto los reportes del día objetivo, el mismo que evalúa la leyenda (TASK-018, TDD).
- [x] 2026-11-01: cliente de IMERG Early diario (`climapp-imerg`) por OPeNDAP de GES DISC: pide solo la celda de la cuenca (~190 bytes por día), con caché, reintentos y el token de Earthdata. Es evidencia satelital de los reportes y se ve en la reproducción; no entra al modelo. Latencia real medida: ~4,5 h (TASK-009b, TDD).
- [x] 2026-11-01: contexto del pronóstico calculado por código: percentil del acumulado de 3 días frente al entrenamiento, climatología del día y riesgo frente al umbral de aviso; la reproducción usa la variante operativa. Muse recibe las cifras en es-CO y la compuerta las compara como números; la explicación de la emisión 2026-10-01 se regrabó con Muse Spark real (TASK-015 y TASK-022, TDD).
- [x] 2026-11-01: revisión visual en el celular. El pronóstico muestra el riesgo, lo normal para esta época y el percentil del acumulado, en es-CO. Cada reporte muestra su resultado en grande, con una frase de por qué y el desglose de evidencia (estaciones, nivel del río y satélite, con ✓/✗ y valores). Los ejemplos usan un punto del cauce del río Pance, y hay un mensaje claro si falla la ubicación (TASK-017, TDD).
- [x] 2026-11-01: el mapa dibuja y encuadra la zona aproximada de la cuenca (provisional), muestra en cada popup el desglose de evidencia y deja sus controles bajo el aviso fijo (TASK-018, TDD).
- [x] 2026-11-01: un mismo texto enviado dos veces en menos de 10 min se marca como duplicado y no se vuelve a pintar; `uv run climapp-demo-reset` vacía los reportes de la base local con confirmación (TASK-016, TDD).
- [x] 2026-11-01: en el desglose de evidencia, el pronóstico va aparte como expectativa y el resultado cuenta solo las fuentes observadas. La explicación de E1 se regrabó con Muse Spark real y el contexto nuevo (TASK-017 y TASK-022, TDD).
- [x] 2026-11-01: se atiende la revisión de Muse del cierre (`docs/reviews/dia-3c.md`): los logs de módulo vuelven a salir en JSON, la caché del explicador incluye las cifras y los duplicados exigen la cuenca y la misma ubicación (TDD).
- [x] 2026-11-02: especificación del set de evaluación de reportes: 50 filas (25 coherentes, 10 exageradas, 10 falsas y 5 difíciles) del periodo de prueba, con etiqueta esperada por una regla escrita sobre los datos (SP-10, SP-17), sin LLM y sin los días de la demo (`eval-harness/`, TASK-021 paso 1, TDD).
- [x] 2026-11-02: set de evaluación de reportes (TASK-021): 50 textos simulados validados sin LLM (campos, prefijo, datos personales y términos prohibidos); los generó Muse Spark 1.3 Contributor por error vía opencode (incidente D-07). Corrida con Muse real, puntuación sin LLM y reintento aparte de los errores de la API (`eval-harness/`, TDD).
- [x] 2026-11-02: tope de tokens de Muse por tarea (estructurar 3000, juez 4000), fijado con la distribución de `tokens_out` de la corrida base: con 2000 se cortaba el 24 % de los juicios (TASK-036, TDD).
- [x] 2026-11-03: dos fallos hallados con el set, corregidos con TDD: una creciente sin afirmación de lluvia ya no cuenta las estaciones, y una cifra con unidad del texto que no queda en `numbers_cited` es `cifra_omitida`. Resultado `base_v2`: 80 % de acierto, 0 exagerados y 0 falsos verificados; el juez high no mejora y se queda medium (TASK-036).
- [x] 2026-11-03: `GET /evaluation` publica `report_verification` con las 4 corridas del set (TASK-036, TDD).

## Herramientas previas al evento, no parte del entregable
Las usamos para trabajar, pero no forman parte de lo que se juzga y ningún archivo suyo está en este repositorio:

- **FORGE**: framework propio de orquestación de agentes para el ciclo de desarrollo.
- **Claude Code**: asistente de programación.
- **Muse Code**: asistente de programación.

## Equipo
- Juan Esteban Gallego
- Juan Manuel Nogales

## Documentación
- [PRD](docs/PRD.md) · [Historias de usuario](docs/user-stories.md) · [Decisiones (ADR)](docs/adr/) · [Modelo de datos](docs/data-model.md) · [API (OpenAPI)](docs/openapi.yaml) · [Backlog](docs/backlog.md) · [MVP](docs/mvp-scope.md) · [DoD](docs/dod.md)

## Fuentes de datos
- Estaciones (lluvia y nivel): CVC — Corporación Autónoma Regional del Valle del Cauca, datos de estaciones (lluvia y nivel) compartidos con autorización (2026-10-31).
- Satélite y malla: NASA GPM IMERG y CHIRPS (UCSB), con sus términos.

Ver [docs/data-sources.md](docs/data-sources.md). Los datos crudos no se versionan.

## Licencia
[MIT](LICENSE)
