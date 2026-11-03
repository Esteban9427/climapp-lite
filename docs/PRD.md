# PRD — ClimApp Lite

> Versión 0.2 · 2026-10-30 · Spec Gate (perfil hackathon) + TASK-020.
> Toda cifra lleva fuente o la marca **SUPUESTO**. Los SUPUESTOS se revisaron con el validador científico (JM) con sus respuestas del 2026-10-29; los que no respondió siguen como SUPUESTO.
> Fuentes citadas: **[INV]** inventario de datos del 2026-10-29 (ver `docs/adr/ADR-004-datos.md`); **[PREV]** análisis exploratorio previo al evento, que todavía no se ha reproducido en este repositorio; **[API]** pruebas de la Meta Model API del 2026-10-29; **[OMM]** OMM-N° 1203, *Directrices de la OMM sobre el cálculo de las normales climáticas*, edición 2017; **[IDEAM]** IDEAM GDI-I001 v02, *Instructivo para la elaboración del mapa de precipitación mensual*, 2025; **[JM]** respuestas del validador científico del 2026-10-29 (**[JM 2026-10-30]**: respuestas sobre calidad de datos del 2026-10-30); **[EVT]** análisis de eventos del 2026-10-30 sobre los datos crudos (solo lectura, ver §Eventos documentados).

## Problema
Quien piensa ir al río Pance (Cali, Colombia) no tiene una forma simple de saber si mañana lloverá fuerte en la cuenca ni si la lluvia de los últimos días aumenta el riesgo de derrumbe. Los pronósticos generales no llegan a la escala de una cuenca corta de montaña, y lo que la gente ve en el terreno no se usa para confirmarlos.

En la cuenca, entre el 6 % y el 13 % de los días registran ≥20 mm en alguna estación, según la estación [INV]. Es un evento frecuente pero difícil de anticipar: la prueba previa detecta el 34 % de los eventos y el 79 % de sus alertas son falsas [PREV]. Por eso el producto es **un pronóstico informativo, no una alerta**.

## Objetivos
1. Publicar cada día un pronóstico de ≥20 mm para mañana que supere a la climatología y a la persistencia en AUC y Brier en el periodo apartado (NFR-5).
2. Verificar el 100 % de los reportes con la compuerta (ADR-002) antes de mostrarlos como verificados.
3. Que ninguna vista con pronóstico se muestre sin el aviso "no es alerta oficial" (R9; test automático).
4. Entregar antes de las 18:00 hora Cali del 2026-11-04 una demo de 3 min que muestre solo lo construido en el evento (R10).

## Usuarios
| Usuario | Necesidad | Señal de éxito |
|---------|-----------|----------------|
| Ciudadano o turista que decide si va al río (principal) | Saber hoy si mañana habrá ≥20 mm en la cuenca y si el acumulado de 3 días es una señal de riesgo | Entiende el pronóstico y la explicación en < 1 min (prueba con 3 personas, SUPUESTO) |
| Ciudadano que confirma ("Waze del clima") | Contar lo que ve, con texto o foto, en segundos | Reporte enviado en < 1 min |
| Validador científico del equipo | Pronóstico evaluado de forma reproducible contra líneas base | `GET /evaluation` con métricas en el periodo apartado |

## Funcionalidades
### IN (v1)
1. **Pronóstico diario**: probabilidad de ≥20 mm mañana en la cuenca (`GET /forecast`), con un modelo entrenado sobre la misma serie satelital que existe en operación (IMERG Early, ADR-001). Umbral de 20 mm/día: fuente [JM], promedio empírico de la lluvia en los días de desbordamiento del río; **confirmado por JM, pendiente de segunda revisión** (SP-10). [OMM] pág. PDF 15 lista ≥5, 10, 50, 100 y 150 mm, pero no 20.
2. **Indicador de acumulado de 3 días** como señal de riesgo de derrumbe. Umbral de 100 mm: SUPUESTO, sin fuente; ocurre en el 1,0 % de los días con la media de la cuenca y en el 2,8 % con el máximo [INV].
3. **Reporte ciudadano** con texto o foto, ubicación y hora (`POST /reports`).
4. **Muse Spark 1.3** (Meta Model API) convierte el reporte en un registro estructurado y explica el pronóstico.
5. **Compuerta de verificación obligatoria** (ADR-002): comprobaciones deterministas, juez Muse Spark y hasta 3 reintentos; si no pasa, el estado es `requiere_revision_humana`.
6. **Confianza calculada por código**, nunca por el modelo; las estaciones correlacionadas cuentan como una sola fuente (ADR-002).
7. **Lista y mapa mínimo** (marcadores) con los reportes verificados y el acierto del pronóstico por día (`GET /reports`, `GET /evaluation`). Pulido del mapa: Should.
8. **Evaluación pública** del modelo contra climatología y persistencia, con y sin EST-B (`GET /evaluation`). Sensibilidades de umbral (10 y 50 mm) y de regla de objetivo, y contraste Early↔Final: Should.
9. **Aviso visible "no es alerta oficial"** y enlace a los canales oficiales en cada vista con pronóstico.
10. **Demo como reproducción histórica** de un evento documentado, sin depender de datos en vivo. Evento aprobado: **E3, 2026-09-30 → 2026-10-02**, con la reproducción de la emisión 2026-10-01 (objetivo 2026-10-02). E1 (2025-01-01) queda como caso de falsa alarma (SP-5, §Eventos documentados).

### OUT (v1)
Sequía e incendios · audio · cuentas de usuario · notificaciones · app nativa · plataforma de consulta histórica · usuarios investigadores · reentrenamiento automático.

## Requisitos no funcionales
| ID | Requisito | Métrica | Fuente |
|----|-----------|---------|--------|
| NFR-1 | Latencia de `GET /forecast` (precalculado) | p95 ≤ 300 ms en el host local | SUPUESTO |
| NFR-2 | Latencia de `POST /reports` con verificación completa | p95 ≤ 30 s con ≤ 3 intentos; la respuesta es asíncrona (`202` + estado) | **No se cumple: limitación de v1.** Medido el 2026-11-03 en el eval-harness (`base_v2`, 50 reportes, Muse real): p50 ≈ 28 s y **p95 ≈ 81 s** por reporte. La respuesta sigue siendo asíncrona; la demo usa respuestas grabadas (`DEMO_FALLBACK=1`, ADR-002 §5) y no muestra esta latencia |
| NFR-3 | Costo por reporte (estructuración + juez, todos los intentos) | ≤ US$0,03 por reporte (p95) | Precios $1,25/M de entrada y $4,25/M de salida [API]; tokens por intento: SUPUESTO (~1,5 k de entrada y ~0,4 k de salida al estructurar, ~2,5 k y ~0,8 k en el juez ≈ US$0,01 por intento). **Medido el 2026-11-03** (`base_v2`, eval-harness): ≈ US$0,021 por reporte en promedio, con todos sus intentos |
| NFR-4 | Cobertura de tests | ≥ 85 % en el núcleo (`core-paths.txt`: forecast, verification) y ≥ 70 % global | Perfil hackathon de FORGE |
| NFR-5 | El modelo supera a las líneas base | AUC y Brier del RF mejores que climatología y persistencia en el periodo apartado | **Cumple (TASK-008, 2026-10-30; se mantiene el 2026-10-31 tras SP-12 y SP-13)**, ver §Resultados del modelo. Previo: AUC 0,75 / 0,66 / 0,57 [PREV], con otra partición |
| NFR-6 | Confianza reproducible | El mismo reporte con la misma evidencia da la misma confianza (función pura, con test) | ADR-002 |
| NFR-7 | Seguridad | Sin secretos en git (gitleaks limpio), SAST sin hallazgos altos y EXIF eliminado de las fotos | Perfil hackathon |
| NFR-8 | Accesibilidad | Contraste WCAG AA y uso desde 360 px de ancho | SUPUESTO |
| NFR-9 | Respuestas del LLM | `max_tokens` ≥ 2000; `finish_reason == "stop"`; contenido no vacío | Con `max_tokens=200` devolvió `content=None` [API] |

## Riesgos
| ID | Riesgo | Impacto | Mitigación |
|----|--------|---------|------------|
| R9 | El producto se interpreta como alerta oficial; un falso negativo puede costar vidas | Crítico | Aviso visible en cada vista, enlace a canales oficiales y texto que comunica la tasa de falsas alarmas; nunca se dice "es seguro ir" |
| R10 | El jurado no distingue lo construido durante el evento y el proyecto queda descalificado | Alto | Sección "Construido durante el evento" en el README, historial de commits desde el 2026-10-29 y demo solo con funciones nuevas |
| R11 | Latencia real de IMERG Early mayor que la prevista (S5) o falla de Earthdata durante el evento | Alto | Medir la latencia real sobre la cuenca (SP-9). Descargar Early 2000→hoy el primer día del sprint y guardarlo en caché con su hash. Si Earthdata falla: plan B (estaciones + CHIRPS en el modelo; IMERG solo como evidencia en la verificación). `data_plan` visible en la API |
| R12 | Datos de estaciones sin autorización de publicación | Alto → **mitigado (2026-10-31)** | **Mitigado:** el propietario de los datos autorizó su uso en el proyecto (D-03 cerrado el 2026-10-31; pendiente adjuntar el soporte escrito). El plan B de datos (solo CHIRPS e IMERG, TASK-035) ya no es necesario. Mientras no se decida otra cosa, el repo sigue sin nombres ni coordenadas de estaciones (EST-A a EST-D, ADR-004) |
| R13 | La API de Muse no responde o se agota la cuota durante la demo | Medio | `DEMO_FALLBACK=1` con respuestas grabadas, marcadas como tales |
| R14 | Las fotos tienen datos personales (caras, placas, EXIF) | Medio | Se elimina el EXIF; en la demo no se guarda el original |
| R15 | Pocos eventos de 3 días ≥100 mm (1 %) | Medio | El indicador se presenta como señal descriptiva, no como predicción evaluada |
| R16 | Las estaciones y CHIRPS no llegan en tiempo real; el pronóstico vigente depende de IMERG Early y de un flujo de estaciones que v1 no tiene | Alto | La variante `operativa` solo usa variables disponibles al día siguiente y es la única que publica `GET /forecast` en vivo; en v1 se emite con el último día de estaciones y queda `stale`. La variante `historica` (con CHIRPS) solo se usa en la reproducción (ADR-001 §3 y §5) |

## Supuestos (revisados en TASK-020 con las respuestas de JM del 2026-10-29)
| ID | Supuesto | Estado |
|----|----------|--------|
| SP-1 | Horizonte: se publican ambos indicadores (mañana ≥20 mm y acumulado de 3 días) | SUPUESTO |
| SP-2 | Día con lluvia = ≥1 mm | Con fuente: [OMM] pág. PDF 14 ("cantidad de días con precipitación ≥1 mm") |
| SP-3 | Categorías de intensidad del IDEAM | **Horarias, no diarias** [JM]: ligera < 2 mm/h, moderada 2-15, fuerte 15-30, muy fuerte o torrencial > 30. Fuente: página del IDEAM, **URL pendiente** (se pide a JM). No se comparan con el umbral diario de 20 mm; se usan solo en el indicador descriptivo de intensidad horaria (ADR-001 §12, TASK-037). [IDEAM] GDI-I001 pág. 12 solo da rangos mensuales |
| SP-4 | Regla de 3 días ≥100 mm | SUPUESTO, sin fuente |
| SP-5 | Evento histórico de la demo | **Cerrado (2026-11-01): E3, 2026-09-30 → 2026-10-02**, decisión del equipo (JE) con los eventos de nivel de JM (tabla de eventos de nivel de la entrega del 2026-11-01). Se reproduce la emisión 2026-10-01 (objetivo 2026-10-02, acierto en las dos variantes). Antes (2026-10-30): E1, 2025-01-01, que **se conserva en los tests como caso de falsa alarma**. Candidatos de JM del 2026-10-29: 2025-01-01 y 2022-02-27 (E2, periodo de validación) |
| SP-6 | Regla del objetivo de cuenca (al menos una estación / media / estación de referencia) | SUPUESTO (JM no respondió); sigue `basin_mean` y se comparan las tres (ADR-001) |
| SP-7 | Estaciones con r ≥ 0,8 agrupadas como una sola fuente | SUPUESTO (JM no respondió; ADR-002) |
| SP-8 | Día válido con ≥ 100 de 144 lecturas | SUPUESTO; [OMM] (pág. PDF 18) e [IDEAM] (pág. 3) solo dan criterios mensuales (11/5 días faltantes; 80 % del mes) |
| SP-9 | La latencia real de IMERG Early sobre la cuenca permite publicar el pronóstico a la hora prevista | **Medida el 2026-11-01 (TASK-009b):** el archivo diario de 2026-10-31 (día UTC, que cierra a las 00:00 UTC del 2026-11-01) se publicó a las 04:30 UTC del 2026-11-01 (`Last-Modified` de GES DISC): unas **4,5 h** tras el cierre del día, 23:30 hora local. Es una sola observación; coincide con la nominal (~4 h). El día UTC termina a las 19:00 hora local, así que el dato de un día está listo antes de la medianoche local. Hoy IMERG Early solo es evidencia de los reportes: el modelo está congelado y no lo usa (TASK-028 queda fuera) |
| SP-10 | Umbral del objetivo: 20 mm/día | **Cerrado** [JM 2026-11-01]: JM lo ratifica ("una buena medida, por encima del promedio", promedio empírico en días de desbordamiento) y, según JM, un segundo experto que consultó coincide |
| SP-11 | Capacidad de JM en el Sprint 1: 8 h | **Confirmado** [JM 2026-10-30] |
| SP-12 | El filtro de picos (> 40 mm en 10 min) basta para descartar artefactos del contador | **Cerrado** [JM 2026-10-30]: no basta. Un salto aislado puede ser una falla de transmisión; hay que mirar si hubo vacíos antes. Regla (ADR-004 §2): un salto ≥ `SUSPECT_STEP_MM` (30 mm, SUPUESTO) que cierra un hueco > `MAX_GAP_MIN` dentro del día es lluvia acumulada (`GAP_INTRADAY`, se conserva). Si lo preceden lecturas regulares con el contador quieto (`SUSPECT_QUIET_MIN` = 60 min sin huecos, con a lo sumo `SUSPECT_QUIET_MAX_MM` = 2 mm [JM 2026-10-30] antes y después), es `suspect` y su lluvia **no** se suma al total diario: queda en `n_suspect` y `suspect_mm`. **Caso E1 (EST-A, 2024-12-31 23:50, +38,6 mm):** las lecturas de la hora previa eran regulares cada 10 min y el contador estaba quieto desde las 21:30; después hay 1,8 mm entre las 00:30 y las 00:50. Se marca `suspect` y el día queda en 14,0 mm. Pero ese mismo día, antes de la calma, el contador bajó de 593,4 a 567,0 a las 17:50, hubo una lectura corrupta a las 20:20 y huecos de 40 y 70 min hasta las 21:30: el salto devuelve el contador a 605,6, 12,2 mm por encima del último valor bueno. Pregunta para JM: ¿esos 12,2 mm pueden ser lluvia real entre las 17:50 y las 23:50? **Respuesta [JM 2026-11-01]: "no es viable en 10 min esa cantidad"**: se mantiene la regla `suspect` y el salto queda excluido. **Cerrado.** En toda la serie quedan 3 días con `suspect`, todos en EST-A (105,3 mm apartados): el 2014-11-30 (día ya inválido), el 2022-12-30 (el contador baja de 60,8 a 27,4 y vuelve exactamente a 60,8: el día pasa de 33,4 a 0,2 mm) y el 2024-12-31 |
| SP-13 | El criterio de día válido (≥ 100/144 lecturas) detecta un sensor que no registra | **Cerrado** [JM 2026-10-30]: no lo detecta. Falla del balancín de EST-B, que no registró lluvia hasta el reinicio. Se declara en el registro versionado `config/known_outages.json` (`KNOWN_OUTAGES_FILE`: `series_id`, `desde`, `hasta`, `motivo`, `fuente`) y sus días quedan `valid=false`. Primer registro: EST-B del 2022-01-01 al 2022-03-01, ambos incluidos; el 2022-03-01 a las 14:00 el contador se pone en 0 (reinicio verificado en los datos). Quedan inválidos 59 días (el 2022-01-17 ya lo era). Nota para JM: el contador vuelve a 0 el 2022-03-07 a las 09:00, tras 1,0 mm; no se incluyó en el periodo. **Respuesta [JM 2026-11-01]:** probablemente fue mantenimiento o una batería que reinició el contador; se trata como un reinicio normal (`RESET`, 0 mm), como ya hace la limpieza. **Cerrado** |
| SP-14 | Un paso del contador sobre un hueco > 20 min (`MAX_GAP_MIN`) que cruza el día local no es lluvia atribuible; dentro del mismo día sí | **Confirmado** [JM 2026-10-30]: los cortes de EST-C fueron fallas de transmisión por la dirección de la antena durante un año, con el contador sumando. Se mantiene la regla de ADR-004 §2, sin cambios de código |
| SP-15 | Pesos de la confianza de los reportes: cada grupo de estaciones 1,0, IMERG Early 0,5 y pronóstico 0,25; lluvia desde 1 mm | **Aceptados por JM para v1** [JM 2026-11-01: "están bien para iniciar"], junto con el peso 1,0 del nivel (SP-17). Se ajustarán con la retroalimentación de los usuarios: trabajo futuro, fuera de v1. Antes: SUPUESTO del equipo (2026-10-31), fijado antes de evaluar la demo (ADR-002 §4). Razones: las estaciones son la verdad de terreno; el satélite es una celda de 0,1° con r entre 0,46 y 0,64 frente a las estaciones; el pronóstico es expectativa, no evidencia. El umbral de 1 mm tiene fuente [OMM] (SP-2). La calibración de los pesos es TASK-021 [Should] |
| SP-16 | Para la demo basta un rectángulo provisional que envuelva el cauce del río Pance (OpenStreetMap, ODbL) para decidir `fuera_de_cuenca` | SUPUESTO aprobado por el equipo (2026-10-31): `data/basin.geojson`, lat 3,266 a 3,369 y lon −76,705 a −76,507 (OSM, ODbL, consultado el 2026-10-31, margen de 0,02°), **en uso hasta que JM aporte el polígono oficial**. El rectángulo incluye zonas fuera de la cuenca, sobre todo en la parte baja y urbana, y puede dejar fuera partes altas de la cabecera; un reporte mal clasificado en el borde es el riesgo aceptado para la demo (ADR-004 §7) |
| SP-17 | Nivel del río como evidencia de crecientes (TASK-039): peso 1,0 (igual que un grupo de estaciones, porque mide directamente lo que el reporte afirma) y subida mínima de 0,30 m en 24 h | **Peso 1,0: aceptado por JM para v1** [JM 2026-11-01, SP-15]. **Umbral de 0,30 m: sigue SUPUESTO, abierto** (JM no ha respondido). **Fijados el 2026-11-01 antes de evaluar la demo** y sin haber visto todavía la serie de nivel (la entrega del 2026-11-01 no estaba en `DATA_DIR`); no se ajustan mirando los resultados de la demo |
| SP-18 | Calidad de la serie de nivel (inventario del 2026-11-01) | **Abierto** (sin respuesta de JM al 2026-11-01, también para los picos de 2014 y 2019). **Pregunta para JM.** (a) 3 383 lecturas negativas (mínimo −0,18 m): ¿cero del sensor desplazado o datos inválidos? (b) Tramos planos en 0,35 m de hasta 6 días (2026-08 y 2026-09, justo antes de E3): ¿es el piso del sensor (el agua por debajo de lo que mide) o el nivel real? Si es el piso, la subida de E3 está subestimada, no inflada. (c) Picos de una sola lectura: se descartan los que saltan y regresan más de `NIVEL_MAX_STEP_M` (**1,0 m, SUPUESTO**); en la serie real son 4 (2014-10-26, 2014-11-28, 2014-12-05 y 2019-03-20, hasta 13,68 m) y los días de E3 no cambian. Las lecturas negativas y el piso no se tocan hasta que JM responda |

## Resultados del modelo (TASK-008, 2026-10-30; regenerados el 2026-10-31 con las correcciones de SP-12 y SP-13)
Periodo apartado de prueba 2023-01-01 → 2026-10-31: 1 388 días evaluables (objetivo observado y dato el día de emisión), 157 eventos (11,3 %). Regla `basin_mean`, umbral 20 mm, `DATA_PLAN=plan_b_earthdata`. Calibración isotónica fuera de muestra 2020-2022 (ADR-001 §1). Todos los modelos se evalúan sobre los mismos días; el umbral de decisión de cada uno se fija fuera de la prueba.

| Modelo | Disponible en vivo | AUC | Brier | POD | FAR | CSI |
|--------|--------------------|-----|-------|-----|-----|-----|
| RF `operativa`, calibrado (publica `GET /forecast`) | Sí | 0,665 | 0,0977 | 0,29 | 0,79 | 0,14 |
| RF `operativa`, sin calibrar | Sí | 0,668 | 0,0972 | 0,29 | 0,79 | 0,14 |
| RF `historica`, calibrado (solo reproducción) | No: CHIRPS llega con semanas de retraso | 0,701 | 0,0962 | 0,43 | 0,79 | 0,17 |
| RF `historica`, sin calibrar | No | 0,715 | 0,0951 | 0,43 | 0,79 | 0,17 |
| Climatología (±15 días) | Sí | 0,627 | 0,0987 | 0,74 | 0,85 | 0,15 |
| Persistencia | Sí | 0,580 | 0,0983 | 0,25 | 0,75 | 0,15 |

- **Antes del cambio de calibración** (isotónica solo en 2022, ADR-001 §1): RF con CHIRPS AUC 0,691 y Brier 0,1009, peor en Brier que la climatología (0,0989) y la persistencia (0,0981). El cambio se decidió después de ver ese resultado; es el único y no se ajusta nada más con la prueba.
- La mejora del RF operativo sobre las líneas base es pequeña en Brier (0,0977 frente a 0,0983) y clara en AUC (0,665 frente a 0,627 y 0,580). Con un 79 % de falsas alarmas, el producto se comunica como informativo (R9).
- **Limitación (2026-11-01): el RF tiende a avisar el día después de que empieza la lluvia.** En los 13 eventos de nivel de JM dentro de la prueba (tabla de eventos de nivel de la entrega del 2026-11-01, desde 2023-01-01), la emisión del día anterior al primer día del evento supera el umbral en **5 de 13** con la variante `operativa` y en **4 de 13** con la `historica`. En los días siguientes del mismo evento acierta más, porque la lluvia ya está en las variables. Se comporta en parte como una persistencia; por eso es un **pronóstico informativo, no una alerta** (R9). Se midió con los artefactos publicados, sin reentrenar ni recalibrar (ADR-001 §1).
- Frente a [PREV] (AUC 0,75 / 0,66 / 0,57): el orden RF > climatología > persistencia se mantiene; el AUC es menor con una partición distinta (prueba 2023-2026 en vez de 2015-2026), la regla `basin_mean` y sin IMERG.

### Cambio por correcciones de calidad de datos (2026-10-31)
**Razón:** correcciones de calidad de datos **decididas por el experto** (JM, 2026-10-30: SP-12 y SP-13), **no por el resultado de la prueba**. No se cambió ningún parámetro del modelo, de la partición ni de la calibración, y `climapp-train` se corrió una sola vez. Los eventos de la prueba no cambian (157 de 1 388 días); en la calibración 2020-2022 pasan de 108 a 110 (2022-02-06: 13,0 → 26,0 mm y 2022-02-27: 19,8 → 39,4 mm, al quedar fuera EST-B), y en el entrenamiento siguen siendo 213. Lo que más cambia es el umbral de decisión que se fija fuera de la prueba: el del RF operativo calibrado pasa de 0,114 a 0,132 y cruza un escalón de la isotónica, así que el POD baja de 0,68 a 0,29 y el FAR de 0,83 a 0,79. AUC y Brier casi no se mueven. Detalle en ADR-001 §Consecuencias.

| Modelo | AUC antes → después | Brier antes → después | POD | FAR | CSI |
|--------|---------------------|-----------------------|-----|-----|-----|
| RF `operativa`, calibrado | 0,664 → 0,665 | 0,0975 → 0,0977 | 0,68 → 0,29 | 0,83 → 0,79 | 0,16 → 0,14 |
| RF `operativa`, sin calibrar | 0,670 → 0,668 | 0,0972 → 0,0972 | 0,61 → 0,29 | 0,82 → 0,79 | 0,16 → 0,14 |
| RF `historica`, calibrado | 0,707 → 0,701 | 0,0962 → 0,0962 | 0,42 → 0,43 | 0,79 → 0,79 | 0,16 → 0,17 |
| RF `historica`, sin calibrar | 0,716 → 0,715 | 0,0949 → 0,0951 | 0,42 → 0,43 | 0,79 → 0,79 | 0,16 → 0,17 |
| Climatología (±15 días) | 0,626 → 0,627 | 0,0987 → 0,0987 | 0,74 → 0,74 | 0,85 → 0,85 | 0,15 → 0,15 |
| Persistencia | 0,580 → 0,580 | 0,0983 → 0,0983 | 0,25 → 0,25 | 0,75 → 0,75 | 0,15 → 0,15 |

**Reproducción de E1, caso de falsa alarma** (`GET /forecast?replay_date=2024-12-31`, objetivo 2025-01-01, media de la cuenca observada 11,2 mm, sin evento):

| Variante | p antes (umbral) | p después (umbral) | Aviso antes → después | `accum_3d_mm` |
|----------|------------------|--------------------|-----------------------|---------------|
| `historica` | 0,146 (0,146) | 0,132 (0,132) | sí, justo en el umbral → sí, justo en el umbral | 50,4 → 40,8 |
| `operativa` | 0,114 (0,114) | 0,149 (0,132) | sí, justo en el umbral → sí, 1,7 puntos por encima | 50,4 → 40,8 |

En las dos versiones E1 sería una falsa alarma frente al objetivo de 20 mm; la creciente ocurrió sin que la cuenca llegara a 20 mm (§Eventos documentados). El acumulado de 3 días baja 9,6 mm, que es el salto de 38,6 mm repartido entre las 4 estaciones. `model_version` pasa de `4959fa8c1e5a` a `c839469b8df2`.

## Eventos documentados
Crecidas citadas por JM como candidatas para la demo. Solo se citan hechos verificados en la fuente; no se publican cifras de víctimas.

| ID | Fecha del hecho | Hecho verificado | Fuente | Periodo (ADR-001 §9) |
|----|-----------------|------------------|--------|----------------------|
| E1 | 2025-01-01 | Creciente súbita del río Pance tras las lluvias de los días anteriores; personas arrastradas por la corriente y operativo de rescate de los organismos de socorro | *El Tiempo*, publicado el 2025-01-02 | **Prueba** |
| E2 | 2022-02-27 (año confirmado por la fuente) | Creciente del río Pance por fuertes lluvias; personas arrastradas por la corriente | *Q'hubo Cali*, publicado el 2022-03-07 | Validación y calibración (no es fuera de muestra) |
| E3 | 2026-09-30 → 2026-10-02 | **Sin fuente de prensa** (búsqueda del 2026-11-01 en El País, El Tiempo, BluRadio y otros medios: la nota más reciente sobre una creciente del Pance es del 2026-04-14). Solo se afirma lo que está en los datos: lluvia en la cuenca y subida del nivel en EST-A (CVC) | Datos de estaciones y nivel (CVC); evento n.º 1 de la tabla de eventos de nivel de JM: 175,6 mm y +0,72 m | **Prueba** |

JM había dado el 2025-01-02 para E1: es la fecha de publicación de la nota; el hecho ocurrió el 1 de enero.

Lluvia diaria (mm, día local) por posición altitudinal (ADR-004) [EVT]. "inv." = día inválido (< 100/144 lecturas); "s/d" = la estación aún no existía (en CHIRPS: la entrega termina el 2026-09-30); "n/d" = la serie de la estación ya terminó (EST-B el 2026-07-07, EST-D el 2025-03-15). Tabla regenerada el 2026-10-31 con las correcciones de SP-12 y SP-13: el salto aislado de E1 ya no se suma (con él, EST-A el 2024-12-31 subía de 14,0 a 52,6 mm) y EST-B queda inválida en E2.

| Evento | Día | EST-C (alta) | EST-B (media-alta) | EST-A (media) | EST-D (piedemonte) | Media de la cuenca | CHIRPS (3 celdas) |
|--------|-----|--------------|--------------------|---------------|--------------------|--------------------|-------------------|
| E1 | D-1 (2024-12-31) | 10,4 | 12,0 | 14,0 | 4,8 | 10,3 | 4,4-5,8 |
| E1 | D (2025-01-01) | 7,6 | 15,6 | 10,4 | inv. | 11,2 | 8,4-11,5 |
| E1 | D+1 (2025-01-02) | 0,1 | 0,2 | 0,2 | 4,5 | 1,3 | 3,7-5,2 |
| E2 | D-1 (2022-02-26) | s/d | inv. (SP-13) | 47,6 | s/d | 47,6 | 15,0-19,1 |
| E2 | D (2022-02-27) | s/d | inv. (SP-13) | 39,4 | s/d | 39,4 | 24,1-30,0 |
| E2 | D+1 (2022-02-28) | s/d | inv. (SP-13) | 6,6 | s/d | 6,6 | 28,5-33,9 |
| E3 | D-1 (2026-09-29) | 0,0 | n/d | 0,0 | n/d | 0,0 | 0,9-2,0 |
| E3 | D (2026-09-30) | 38,4 | n/d | 125,4 | n/d | 81,9 | 5,2-8,1 |
| E3 | D+1 (2026-10-01) | 16,9 | n/d | 6,6 | n/d | 11,8 | s/d |
| E3 | D+2 (2026-10-02) | 32,3 | n/d | 43,6 | n/d | 38,0 | s/d |

- **Acumulado de 3 días (D-2 a D):** E1: 34,8 mm (EST-A), 47,2 (EST-B), 39,6 (EST-C); media de la cuenca 35,4. E2: 87,6 mm (EST-A); media de la cuenca 87,6 (solo EST-A: EST-B queda inválida por SP-13; antes, 43,9). Ninguno llega al umbral de 100 mm (SP-4).
- **Máxima intensidad horaria** (ventana móvil de 6 lecturas de 10 min, D-1 a D+1): E1: 6,0 mm/h (EST-B), **moderada**; ninguna estación pasa de moderada. E2: 15,2 mm/h (EST-A, 2022-02-26), **fuerte**. Con el salto de SP-12, E1 aparecería como "torrencial" (38,6-40,2 mm/h): por eso el indicador excluye los saltos `suspect` y muestra también la lectura máxima de 10 min.
- **CHIRPS:** cubre los dos eventos (las 3 celdas con dato). Agrega por día UTC (ADR-004 §1).
- **Lectura honesta de E1:** la creciente ocurrió sin que la media de la cuenca llegara a 20 mm en D-1 ni en D. El producto pronostica lluvia, no crecientes, y la demo debe decirlo (R9).
- **E3, nivel del río en EST-A (subida máxima en 24 h, `climapp-level`):** 2026-09-29: 0,01 m (nivel 0,34-0,35 m); 2026-09-30: 0,16 m (0,35-0,51 m); 2026-10-01: 0,47 m (0,39-0,86 m); **2026-10-02: 0,68 m** (0,41 m a las 14:40 y **1,07 m a las 16:10**). JM mide +0,72 m sobre todo el evento; climapp-level usa una ventana de 24 h.
- **E3, acumulado de 3 días hasta la emisión (2026-09-29 a 2026-10-01):** 93,7 mm de media en la cuenca: "normal", bajo el umbral de 100 mm (SP-4). CHIRPS ve 5,2-8,1 mm el 2026-09-30, frente a 81,9 mm de las estaciones.
- **Reproducción de E3** (`GET /forecast?replay_date=2026-10-01`, objetivo 2026-10-02, media de la cuenca observada 38,0 mm): `historica` 0,1324 (umbral 0,1324, justo en el umbral) y `operativa` 0,149 (umbral 0,132): **acierto en las dos**. Lectura honesta: el primer día (2026-09-30, 81,9 mm) fue un **fallo** (emisión 2026-09-29: `operativa` 0,112 y `historica` 0,117, bajo el umbral), y el 2026-10-01 (11,8 mm) una **falsa alarma** (0,200 y 0,222). Es la limitación de §Resultados del modelo: el aviso llega el día después de que empieza la lluvia.
- **Reportes de ejemplo de E3 (simulados, `config/demo_reports.json`), tarde del 2026-10-02 (`DEMO_REPORT_TIME` 16:30), grabados con Muse Spark real el 2026-11-01 (ADR-002, corrida 5):** el verdadero ("el río creció", parte media) queda `verificado` con confianza 100 %: las estaciones, el pronóstico y la subida de nivel concuerdan. El exagerado ("se desbordó y arrasó con todas las casas") va a `requiere_revision_humana`: el juez no encontró respaldo en el texto en los 3 intentos. El falso ("no ha caído ni una gota") queda `verificado` con confianza 0 %, porque nada lo respalda. La confianza mide si llovió o si el río subió, no cuánto; el exagerado no lo frenó la confianza sino la compuerta.
- **Mapa de E3:** en una reproducción, el mapa muestra por defecto los reportes del día objetivo (desde el 2026-11-01). `/mapa?replay_date=2026-10-01` muestra los reportes de ejemplo observados el 2026-10-02 y "Pronóstico para el 2026-10-02: acierto".
- **Recomendación (2026-11-01):** E3 para la demo. Está en el periodo de prueba, es el de mayor lluvia entre los eventos de nivel de JM (175,6 mm) y el más reciente, con una subida clara del nivel (0,68 m en 24 h; otros eventos subieron más, hasta 1,14 m), y su reproducción es un acierto honesto, con el fallo del primer día dicho en voz alta. E1 se conserva como caso de falsa alarma: la creciente ocurrió sin llegar a 20 mm en la cuenca. E2 sigue como ejemplo de lluvia de varios días del periodo de validación.
