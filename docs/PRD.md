# PRD — ClimApp Lite

> Versión 0.1 · 2026-10-29 · Spec Gate (perfil hackathon).
> Toda cifra lleva fuente o la marca **SUPUESTO**. Los SUPUESTOS se revisan con el validador científico el 2026-10-30 a las 12:00.
> Fuentes citadas: **[INV]** inventario de datos del 2026-10-29 (ver `docs/adr/ADR-004-datos.md`); **[PREV]** análisis exploratorio previo al evento, que todavía no se ha reproducido en este repositorio; **[API]** pruebas de la Meta Model API del 2026-10-29; **[OMM]** OMM-N° 1203, *Directrices de la OMM sobre el cálculo de las normales climáticas*, edición 2017; **[IDEAM]** IDEAM GDI-I001 v02, *Instructivo para la elaboración del mapa de precipitación mensual*, 2025.

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
1. **Pronóstico diario**: probabilidad de ≥20 mm mañana en la cuenca (`GET /forecast`). El umbral de 20 mm es SUPUESTO: [OMM] pág. PDF 15 lista ≥5, 10, 50, 100 y 150 mm, pero no 20.
2. **Indicador de acumulado de 3 días** como señal de riesgo de derrumbe. Umbral de 100 mm: SUPUESTO, sin fuente; ocurre en el 1,0 % de los días con la media de la cuenca y en el 2,8 % con el máximo [INV].
3. **Reporte ciudadano** con texto o foto, ubicación y hora (`POST /reports`).
4. **Muse Spark 1.3** (Meta Model API) convierte el reporte en un registro estructurado y explica el pronóstico.
5. **Compuerta de verificación obligatoria** (ADR-002): comprobaciones deterministas, juez Muse Spark y hasta 3 reintentos; si no pasa, el estado es `requiere_revision_humana`.
6. **Confianza calculada por código**, nunca por el modelo; las estaciones correlacionadas cuentan como una sola fuente (ADR-002).
7. **Mapa** con los reportes y el acierto del pronóstico por día (`GET /reports`, `GET /evaluation`).
8. **Evaluación pública** del modelo contra climatología y persistencia (`GET /evaluation`).
9. **Aviso visible "no es alerta oficial"** y enlace a los canales oficiales en cada vista con pronóstico.
10. **Demo como reproducción histórica** de un evento documentado, sin depender de datos en vivo. Evento por definir (SUPUESTO).

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
| R11 | Desfase Final→Early: se entrena con IMERG Final y en operación solo hay Early | Alto | Descargar Early y Final de 2025 a hoy, medir sesgo y correlación y publicarlos en `GET /evaluation`. Variante obligatoria "operativa" (estaciones + Early) evaluada aparte |
| R12 | Datos de estaciones sin autorización de publicación | Alto | Repo sin nombres ni coordenadas de estaciones (ADR-004). Plan B: modelo y demo solo con CHIRPS e IMERG |
| R13 | La API de Muse no responde o se agota la cuota durante la demo | Medio | `DEMO_FALLBACK=1` con respuestas grabadas, marcadas como tales |
| R14 | Las fotos tienen datos personales (caras, placas, EXIF) | Medio | Se elimina el EXIF; en la demo no se guarda el original |
| R15 | Pocos eventos de 3 días ≥100 mm (1 %) | Medio | El indicador se presenta como señal descriptiva, no como predicción evaluada |

## Supuestos (SUPUESTO hasta el 2026-10-30)
| ID | Supuesto | Estado |
|----|----------|--------|
| SP-1 | Horizonte: se publican ambos indicadores (mañana ≥20 mm y acumulado de 3 días) | SUPUESTO |
| SP-2 | Día con lluvia = ≥1 mm | Con fuente: [OMM] pág. PDF 14 ("cantidad de días con precipitación ≥1 mm") |
| SP-3 | Categorías de intensidad IDEAM/OMM | **Sin fuente**: ninguno de los dos documentos define categorías de intensidad diaria. [IDEAM] pág. 12 solo da rangos mensuales para el mapa. SUPUESTO |
| SP-4 | Regla de 3 días ≥100 mm | SUPUESTO, sin fuente |
| SP-5 | Evento histórico de la demo | Por definir |
| SP-6 | Regla del objetivo de cuenca (al menos una estación / media / estación de referencia) | SUPUESTO; se comparan las tres (ADR-001) |
| SP-7 | Estaciones con r ≥ 0,8 agrupadas como una sola fuente | SUPUESTO (ADR-002) |
| SP-8 | Día válido con ≥ 100 de 144 lecturas | SUPUESTO; [OMM] (pág. PDF 18) e [IDEAM] (pág. 3) solo dan criterios mensuales (11/5 días faltantes; 80 % del mes) |
| SP-9 | La latencia real de IMERG Early sobre la cuenca permite publicar el pronóstico a la hora prevista | Pendiente de medir |
