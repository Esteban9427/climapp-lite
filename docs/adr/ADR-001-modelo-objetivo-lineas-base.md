# ADR-001: Modelo de pronóstico, objetivo de cuenca y líneas base

- **Estado:** Aceptado con SUPUESTOS (revisado en TASK-020 con las respuestas de JM del 2026-10-29)
- **Fecha:** 2026-10-29
- **Relacionados:** ADR-004 (datos), PRD §Funcionalidades 1-2, NFR-5, R11
- **Revisado:** 2026-10-29 (IMERG Early como serie principal; Final solo como contraste) · 2026-10-30 (fuente del umbral; §12 intensidad horaria observada) · 2026-10-30, tarde (§1 calibración fuera de muestra; §3 y §5 variantes operativa e histórica; §9 partición)

## Contexto
Se necesita la probabilidad de que mañana caiga ≥20 mm en la cuenca del río Pance. La cuenca es corta y tiene cuatro estaciones pluviométricas (alta, media-alta, media y piedemonte) con periodos distintos (ADR-004). Las correlaciones diarias por pares van de 0,49 a 0,88 [INV 2026-10-29]. La frecuencia de días ≥20 mm varía entre el 6,3 % y el 13,2 % según la estación [INV]. Una prueba exploratoria previa al evento (RF entrenado hasta 2014 y probado en 2015-2026) obtuvo AUC 0,75 frente a 0,66 de la climatología y 0,57 de la persistencia, detectó el 34 % de los eventos y el 79 % de sus alertas fueron falsas. No se ha reproducido aquí; se regenera con TDD.

## Decisión
1. **Modelo:** random forest de clasificación (scikit-learn), con salida de probabilidad calibrada. No se busca otro algoritmo en v1.
   - **Calibración (revisada el 2026-10-30, tarde):** isotónica sobre predicciones **fuera de muestra de 2020, 2021 y 2022**. Para cada año se entrena un bosque con las fechas objetivo anteriores y se predice ese año; el bosque final se entrena con todo lo previo a la prueba (2013-10 → 2022-12). El umbral de decisión de POD, FAR y CSI se fija sobre esas mismas predicciones fuera de muestra.
   - **Transparencia:** el cambio **se decidió después de ver el Brier de prueba**. Con la isotónica ajustada solo en 2022, el Brier del RF (0,1009) era peor que el de la climatología (0,0989) y el de la persistencia (0,0981). La razón metodológica: 2022 tiene **24 eventos en 364 días (6,6 %)**, frente al 10,2 % del entrenamiento y el 11,3 % de la prueba; son muy pocos para calibrar y bajaban las probabilidades (media de 0,067 frente a 0,113 observado). El hallazgo SP-13 (EST-B sin registrar a comienzos de 2022) solo explica medio punto (6,6 → 7,1 %).
   - **Condición:** es el **único** cambio hecho mirando la prueba. Su resultado se publica tal cual, sea mejor o peor que las líneas base, y no se vuelve a ajustar nada con la prueba. `GET /evaluation` y el PRD reportan el RF calibrado y sin calibrar junto a las dos líneas base.
   - Consecuencia del cambio de partición: la climatología y la persistencia se ajustan también con todo lo previo a la prueba (≤ 2022), igual que el bosque final.
2. **Objetivo "≥20 mm en la cuenca":** se comparan tres reglas, todas sobre días válidos (ADR-004):
   | Regla | Definición | Frecuencia [INV] |
   |-------|------------|------------------|
   | A. Al menos una estación | máx. de las estaciones válidas ≥ 20 mm | 16,0 % |
   | B. Media de la cuenca | media de las estaciones válidas ≥ 20 mm | 10,2 % |
   | C. Estación de referencia | la serie más larga y más reciente (EST-A; elección SUPUESTO) ≥ 20 mm | 9,6 % |
   **Umbral:** 20 mm/día. Fuente: [JM], promedio empírico de la lluvia en los días de desbordamiento del río. Estado: **confirmado por JM, pendiente de segunda revisión** (PRD SP-10).
   **Regla principal:** `TARGET_RULE=basin_mean` (B), SUPUESTO: el validador científico no se pronunció (respuestas del 2026-10-29). Las reglas A y C se reportan como **sensibilidad [Should]**.
3. **Variables:**
   - Agregados de la cuenca del día t, t-1 y t-2: media, máximo y dispersión (desviación estándar), **calculados con las estaciones disponibles ese día** (los días válidos de cada una). Se incluye el número de estaciones disponibles como variable, para que el modelo sepa cuántas entran en cada agregado.
   - Acumulado de 3 días de la media de la cuenca.
   - Satélite: **IMERG Early V07 diario (`GPM_3IMERGDE`)** en la celda de 0,1°, desde el inicio del registro (2000) hasta hoy. Es la misma serie que existe en operación, así que no hay desfase entre entrenamiento y servicio. Las celdas CHIRPS de la cuenca entran como variable histórica y como climatología.
   - **Variantes (decisión del 2026-10-30, por disponibilidad de datos y no por el resultado de la prueba):** el mismo pipeline produce dos modelos.
     - **`operativa`**: solo variables disponibles al día siguiente. Hoy son las estaciones; IMERG Early se suma cuando entre TASK-028. Es la que publica `GET /forecast` fuera del modo de reproducción.
     - **`historica`**: agrega CHIRPS, que publica con semanas de retraso (el archivo actual termina el 2026-09-30). Se usa **solo** en la reproducción histórica de la demo (E1), y `GET /evaluation` la etiqueta "requiere datos con semanas de retraso; no disponible en vivo".
     - Las dos se calibran igual (§1), sin más ajustes mirando la prueba, y sus métricas se reportan juntas, con las líneas base.
   - Estacionalidad: seno y coseno del día del año.
   - Comparación con estaciones individuales en lugar de agregados: **[Should]**.
4. **IMERG Final** (`GPM_3IMERGDF`, el CSV satelital histórico) **no entra al modelo**. Solo sirve de contraste: el sesgo y la correlación Early↔Final se reportan en `GET /evaluation` **[Should]**.
5. **Plan B si Earthdata falla** (no se puede descargar Early): el modelo usa estaciones + CHIRPS, e IMERG queda solo como evidencia en la verificación de reportes (ADR-002). `GET /evaluation` indica qué plan está activo.
   - Revisión del 2026-10-30: en el plan B, la variante `operativa` usa solo estaciones y la `historica` estaciones + CHIRPS (§3). Ni las estaciones ni CHIRPS llegan en tiempo real (PRD R16): en v1 el pronóstico vigente se calcula con el último día de estaciones disponible y queda marcado `stale`.
6. **Robustez ante la pérdida de una estación:** EST-B deja de reportar el 2026-07-07. El modelo es robusto por diseño (los agregados usan las estaciones disponibles; Must). El **informe comparativo con y sin EST-B** es **[Should]** por capacidad (TASK-029): se evalúa (sin EST-B = sus días se tratan como no disponibles en todo el periodo de prueba) y se reportan ambas métricas. Como los agregados usan las estaciones disponibles, el modelo sigue funcionando sin EST-B.
7. **Sensibilidad del umbral [Should]:** 10 y 50 mm además de 20 mm (SUPUESTO). Las tres frecuencias y métricas se reportan; el producto publica solo 20 mm.
8. **Líneas base:**
   - Climatología: frecuencia del evento por día del año (ventana de ±15 días) en el periodo de entrenamiento.
   - Persistencia: P(mañana) = 1 si hoy ≥ 20 mm; si no, 0. Para Brier y AUC se usa la frecuencia condicional del entrenamiento.
9. **Partición temporal (SUPUESTO; revisada el 2026-10-30, tarde, ver §1):**
   - Entrenamiento del bosque final: 2013-10 → 2022-12 (`TRAIN_START` → `VALID_END`).
   - Calibración y validación fuera de muestra, por años: 2020 → 2022 (`CALIBRATION_START` → `VALID_END`). Cada año la predice un bosque entrenado solo con los años anteriores.
   - Periodo apartado de prueba: 2023-01 → 2026-10 (`TEST_END`).
   - Cada muestra pertenece al periodo de su fecha objetivo. Nada del periodo de prueba toca el entrenamiento ni la calibración (test de fuga). Los días imputados nunca entran en la evaluación (ADR-004).
10. **Métricas:** aciertos (POD), falsas alarmas (FAR), CSI, Brier, AUC y curva de calibración. El umbral de decisión para POD, FAR y CSI se fija en validación, nunca en prueba.
11. **Acumulado de 3 días:** es un indicador descriptivo, no un pronóstico evaluado. El umbral de 100 mm es SUPUESTO y no tiene fuente: [OMM] pág. PDF 15 lista ≥50, 100 y 150 mm como umbrales de recuento diario, no de 3 días. Ocurre en el 1,0 % de los días con la media de la cuenca y en el 2,8 % con el máximo [INV].
12. **Intensidad horaria observada [Should, TASK-037, JE, 1,5 h]:** indicador **descriptivo** de lo que ya llovió, nunca objetivo del modelo.
    - Por estación y día: máximo de la suma móvil de 6 lecturas consecutivas de 10 min (solo ventanas sin huecos), con la categoría del IDEAM [JM]: ligera < 2 mm/h, moderada 2-15, fuerte 15-30, muy fuerte o torrencial > 30. Fuente: página del IDEAM, URL pendiente (PRD SP-3).
    - Son intensidades **horarias**: no se comparan con el umbral diario de 20 mm ni con el acumulado de 3 días.
    - Junto a la categoría se muestra la lectura máxima de 10 min de la ventana, para que un salto aislado del contador no pase por lluvia torrencial (PRD SP-12: en E1, un solo salto de 38,6 mm convierte una hora sin lluvia en "torrencial").
    - Se calcula con las lecturas limpias de ADR-004 §2; si la estación no tiene ventanas completas ese día, el indicador queda vacío.

## Consecuencias
- Positivas: el modelo es simple, explicable y comparable con líneas base honestas. Al entrenarse con Early, la evaluación ya es la del modelo operativo: no hace falta una variante aparte.
- Negativas: con un 79 % de falsas alarmas [PREV], el producto se comunica como informativo (R9). Las series cortas (EST-C y EST-D) limitan la regla A en los años anteriores a 2023.
- Si el RF no supera a la climatología en el periodo apartado, se publica igual y el pitch lo dice (NFR-5).

## Alternativas descartadas
- Gradient boosting o redes: más ajuste y menos explicables, con poca ganancia esperada sobre unos 4 600 días.
- Evaluación aleatoria (k-fold): filtra autocorrelación temporal.
