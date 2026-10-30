# PRD — ClimApp Lite

> Versión 0.2 · 2026-10-30 · Spec Gate (perfil hackathon) + TASK-020.
> Toda cifra lleva fuente o la marca **SUPUESTO**. Los SUPUESTOS se revisaron con el validador científico (JM) con sus respuestas del 2026-10-29; los que no respondió siguen como SUPUESTO.
> Fuentes citadas: **[INV]** inventario de datos del 2026-10-29 (ver `docs/adr/ADR-004-datos.md`); **[PREV]** análisis exploratorio previo al evento, que todavía no se ha reproducido en este repositorio; **[API]** pruebas de la Meta Model API del 2026-10-29; **[OMM]** OMM-N° 1203, *Directrices de la OMM sobre el cálculo de las normales climáticas*, edición 2017; **[IDEAM]** IDEAM GDI-I001 v02, *Instructivo para la elaboración del mapa de precipitación mensual*, 2025; **[JM]** respuestas del validador científico del 2026-10-29; **[EVT]** análisis de eventos del 2026-10-30 sobre los datos crudos (solo lectura, ver §Eventos documentados).

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
10. **Demo como reproducción histórica** de un evento documentado, sin depender de datos en vivo. Evento recomendado: 2025-01-01 (SP-5, §Eventos documentados).

### OUT (v1)
Sequía e incendios · audio · cuentas de usuario · notificaciones · app nativa · plataforma de consulta histórica · usuarios investigadores · reentrenamiento automático.

## Requisitos no funcionales
| ID | Requisito | Métrica | Fuente |
|----|-----------|---------|--------|
| NFR-1 | Latencia de `GET /forecast` (precalculado) | p95 ≤ 300 ms en el host local | SUPUESTO |
| NFR-2 | Latencia de `POST /reports` con verificación completa | p95 ≤ 30 s con ≤ 3 intentos; la respuesta es asíncrona (`202` + estado) | SUPUESTO; se mide en el eval-harness |
| NFR-3 | Costo por reporte (estructuración + juez, todos los intentos) | ≤ US$0,03 por reporte (p95) | Precios $1,25/M de entrada y $4,25/M de salida [API]; tokens por intento: SUPUESTO (~1,5 k de entrada y ~0,4 k de salida al estructurar, ~2,5 k y ~0,8 k en el juez ≈ US$0,01 por intento) |
| NFR-4 | Cobertura de tests | ≥ 85 % en el núcleo (`core-paths.txt`: forecast, verification) y ≥ 70 % global | Perfil hackathon de FORGE |
| NFR-5 | El modelo supera a las líneas base | AUC y Brier del RF mejores que climatología y persistencia en el periodo apartado | Previo: AUC 0,75 / 0,66 / 0,57 [PREV]; se regenera |
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
| R12 | Datos de estaciones sin autorización de publicación | Alto | Repo sin nombres ni coordenadas de estaciones (ADR-004). Plan B: modelo y demo solo con CHIRPS e IMERG |
| R13 | La API de Muse no responde o se agota la cuota durante la demo | Medio | `DEMO_FALLBACK=1` con respuestas grabadas, marcadas como tales |
| R14 | Las fotos tienen datos personales (caras, placas, EXIF) | Medio | Se elimina el EXIF; en la demo no se guarda el original |
| R15 | Pocos eventos de 3 días ≥100 mm (1 %) | Medio | El indicador se presenta como señal descriptiva, no como predicción evaluada |

## Supuestos (revisados en TASK-020 con las respuestas de JM del 2026-10-29)
| ID | Supuesto | Estado |
|----|----------|--------|
| SP-1 | Horizonte: se publican ambos indicadores (mañana ≥20 mm y acumulado de 3 días) | SUPUESTO |
| SP-2 | Día con lluvia = ≥1 mm | Con fuente: [OMM] pág. PDF 14 ("cantidad de días con precipitación ≥1 mm") |
| SP-3 | Categorías de intensidad del IDEAM | **Horarias, no diarias** [JM]: ligera < 2 mm/h, moderada 2-15, fuerte 15-30, muy fuerte o torrencial > 30. Fuente: página del IDEAM, **URL pendiente** (se pide a JM). No se comparan con el umbral diario de 20 mm; se usan solo en el indicador descriptivo de intensidad horaria (ADR-001 §12, TASK-037). [IDEAM] GDI-I001 pág. 12 solo da rangos mensuales |
| SP-4 | Regla de 3 días ≥100 mm | SUPUESTO, sin fuente |
| SP-5 | Evento histórico de la demo | Candidatos de JM: 2025-01-01 y 2022-02-27 (fechas corregidas con la prensa). **Recomendado: 2025-01-01** (único en el periodo de prueba). Pendiente de aprobación del equipo |
| SP-6 | Regla del objetivo de cuenca (al menos una estación / media / estación de referencia) | SUPUESTO (JM no respondió); sigue `basin_mean` y se comparan las tres (ADR-001) |
| SP-7 | Estaciones con r ≥ 0,8 agrupadas como una sola fuente | SUPUESTO (JM no respondió; ADR-002) |
| SP-8 | Día válido con ≥ 100 de 144 lecturas | SUPUESTO; [OMM] (pág. PDF 18) e [IDEAM] (pág. 3) solo dan criterios mensuales (11/5 días faltantes; 80 % del mes) |
| SP-9 | La latencia real de IMERG Early sobre la cuenca permite publicar el pronóstico a la hora prevista | Pendiente de medir |
| SP-10 | Umbral del objetivo: 20 mm/día | Confirmado por JM (promedio empírico en días de desbordamiento), **pendiente de segunda revisión** |
| SP-11 | Capacidad de JM en el Sprint 1: 8 h | Declarada por JM, **por confirmar** |
| SP-12 | El filtro de picos (> 40 mm en 10 min) basta para descartar artefactos del contador | **En duda** [EVT]: un salto aislado de 38,6 mm en una sola lectura de 10 min, con la hora anterior y la posterior en 0, pasa el filtro y fabrica un día de 52,6 mm y una hora "torrencial". Pregunta abierta para JM |
| SP-13 | El criterio de día válido (≥ 100/144 lecturas) detecta un sensor que no registra | **No lo detecta** [EVT]: EST-B suma ≈ 6 mm entre el 2022-01-01 y el 2022-03-01 con días completos de lecturas, mientras EST-A registra días de 40-52 mm. Pregunta abierta para JM |

## Eventos documentados
Crecidas citadas por JM como candidatas para la demo. Solo se citan hechos verificados en la fuente; no se publican cifras de víctimas.

| ID | Fecha del hecho | Hecho verificado | Fuente | Periodo (ADR-001 §9) |
|----|-----------------|------------------|--------|----------------------|
| E1 | 2025-01-01 | Creciente súbita del río Pance tras las lluvias de los días anteriores; personas arrastradas por la corriente y operativo de rescate de los organismos de socorro | *El Tiempo*, publicado el 2025-01-02 | **Prueba** |
| E2 | 2022-02-27 (año confirmado por la fuente) | Creciente del río Pance por fuertes lluvias; personas arrastradas por la corriente | *Q'hubo Cali*, publicado el 2022-03-07 | Validación y calibración (no es fuera de muestra) |

JM había dado el 2025-01-02 para E1: es la fecha de publicación de la nota; el hecho ocurrió el 1 de enero.

Lluvia diaria (mm, día local) por posición altitudinal (ADR-004) [EVT]. "inv." = día inválido (< 100/144 lecturas); "s/d" = la estación aún no existía. E1 se muestra **sin** el salto aislado de SP-12 (con él, EST-A el 2024-12-31 sube de 14,0 a 52,6 mm).

| Evento | Día | EST-C (alta) | EST-B (media-alta) | EST-A (media) | EST-D (piedemonte) | Media de la cuenca | CHIRPS (3 celdas) |
|--------|-----|--------------|--------------------|---------------|--------------------|--------------------|-------------------|
| E1 | D-1 (2024-12-31) | 10,4 | 12,0 | 14,0 | 4,8 | 10,3 | 4,4-5,8 |
| E1 | D (2025-01-01) | 7,6 | 15,6 | 10,4 | inv. | 11,2 | 8,4-11,5 |
| E1 | D+1 (2025-01-02) | 0,1 | 0,2 | 0,2 | 4,5 | 1,3 | 3,7-5,2 |
| E2 | D-1 (2022-02-26) | s/d | 0,0 (SP-13) | 47,6 | s/d | 23,8 | 15,0-19,1 |
| E2 | D (2022-02-27) | s/d | 0,2 (SP-13) | 39,4 | s/d | 19,8 | 24,1-30,0 |
| E2 | D+1 (2022-02-28) | s/d | 0,1 (SP-13) | 6,6 | s/d | 3,3 | 28,5-33,9 |

- **Acumulado de 3 días (D-2 a D):** E1: 34,8 mm (EST-A), 47,2 (EST-B), 39,6 (EST-C); media de la cuenca 35,4. E2: 87,6 mm (EST-A); media de la cuenca 43,9 (baja por EST-B). Ninguno llega al umbral de 100 mm (SP-4).
- **Máxima intensidad horaria** (ventana móvil de 6 lecturas de 10 min, D-1 a D+1): E1: 6,0 mm/h (EST-B), **moderada**; ninguna estación pasa de moderada. E2: 15,2 mm/h (EST-A, 2022-02-26), **fuerte**. Con el salto de SP-12, E1 aparecería como "torrencial" (38,6-40,2 mm/h): por eso el indicador muestra también la lectura máxima de 10 min.
- **CHIRPS:** cubre los dos eventos (las 3 celdas con dato). Agrega por día UTC (ADR-004 §1).
- **Lectura honesta de E1:** la creciente ocurrió sin que la media de la cuenca llegara a 20 mm en D-1 ni en D. El producto pronostica lluvia, no crecientes, y la demo debe decirlo (R9).
- **Recomendación:** E1 para la demo, porque es el único en el periodo de prueba (una reproducción de E2 usaría el año con el que se calibra el modelo y se fija el umbral de decisión). E2 sirve como ejemplo de lluvia de varios días, marcado como periodo de validación.
