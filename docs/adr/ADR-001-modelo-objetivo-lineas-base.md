# ADR-001: Modelo de pronóstico, objetivo de cuenca y líneas base

- **Estado:** Aceptado con SUPUESTOS (revisión el 2026-10-30, 12:00)
- **Fecha:** 2026-10-29
- **Relacionados:** ADR-004 (datos), PRD §Funcionalidades 1-2, NFR-5

## Contexto
Se necesita la probabilidad de que mañana caiga ≥20 mm en la cuenca del río Pance. La cuenca es corta y tiene cuatro estaciones pluviométricas (parte media y parte alta) con periodos distintos (ADR-004). Las correlaciones diarias por pares van de 0,49 a 0,88 [INV 2026-10-29]. La frecuencia de días ≥20 mm varía entre el 6,3 % y el 13,2 % según la estación [INV]. Una prueba exploratoria previa al evento (RF entrenado hasta 2014 y probado en 2015-2026) obtuvo AUC 0,75 frente a 0,66 de la climatología y 0,57 de la persistencia, detectó el 34 % de los eventos y el 79 % de sus alertas fueron falsas. No se ha reproducido aquí; se regenera con TDD.

## Decisión
1. **Modelo:** random forest de clasificación (scikit-learn), con salida de probabilidad calibrada (isotónica sobre el bloque de validación). No se busca otro algoritmo en v1.
2. **Objetivo "≥20 mm en la cuenca":** se comparan tres reglas, todas sobre días válidos (ADR-004):
   | Regla | Definición | Frecuencia [INV] |
   |-------|------------|------------------|
   | A. Al menos una estación | máx. de las estaciones válidas ≥ 20 mm | 16,0 % |
   | B. Media de la cuenca | media de las estaciones válidas ≥ 20 mm | 10,2 % |
   | C. Estación de referencia | la serie más larga y más reciente (EST-A; elección SUPUESTO) ≥ 20 mm | 9,6 % |
   Regla por defecto: **B (SUPUESTO)** hasta la respuesta del validador científico. Las tres se reportan en `GET /evaluation`.
3. **Variables:**
   - Agregados de la cuenca del día t, t-1 y t-2: media, máximo y desviación estándar entre estaciones.
   - Acumulado de 3 días.
   - Satélite: IMERG Final en la celda de 0,1° (**una sola serie**) y las celdas CHIRPS de la cuenca.
   - Estacionalidad: seno y coseno del día del año.
   - **Comparación obligatoria:** el mismo modelo con estaciones individuales en lugar de agregados.
4. **Variante operativa (obligatoria, R11):** un modelo que usa solo variables disponibles al día siguiente (estaciones + IMERG **Early**), evaluado aparte. El sesgo y la correlación Final↔Early de 2025 a hoy se publican.
5. **Líneas base:**
   - Climatología: frecuencia del evento por día del año (ventana de ±15 días) en el periodo de entrenamiento.
   - Persistencia: P(mañana) = 1 si hoy ≥ 20 mm; si no, 0. Para Brier y AUC se usa la frecuencia condicional del entrenamiento.
6. **Partición temporal (SUPUESTO):**
   - Entrenamiento: 2013-10 → 2021-12.
   - Validación y calibración: 2022.
   - Periodo apartado de prueba: 2023-01 → 2026-10.
   - Nada del periodo de prueba toca el entrenamiento ni la calibración. Los días imputados nunca entran en la evaluación (ADR-004).
7. **Métricas:** aciertos (POD), falsas alarmas (FAR), CSI, Brier, AUC y curva de calibración. El umbral de decisión para POD, FAR y CSI se fija en validación, nunca en prueba.
8. **Acumulado de 3 días:** es un indicador descriptivo, no un pronóstico evaluado. El umbral de 100 mm es SUPUESTO y no tiene fuente: [OMM] pág. PDF 15 lista ≥50, 100 y 150 mm como umbrales de recuento diario, no de 3 días. Ocurre en el 1,0 % de los días con la media de la cuenca y en el 2,8 % con el máximo [INV].

## Consecuencias
- Positivas: el modelo es simple, explicable y comparable con líneas base honestas, y la variante operativa muestra el desempeño realista.
- Negativas: con un 79 % de falsas alarmas [PREV], el producto se comunica como informativo (R9). Las series cortas (EST-C y EST-D) limitan la regla A en los años anteriores a 2023.
- Si el RF no supera a la climatología en el periodo apartado, se publica igual y el pitch lo dice (NFR-5).

## Alternativas descartadas
- Gradient boosting o redes: más ajuste y menos explicables, con poca ganancia esperada sobre unos 4 600 días.
- Evaluación aleatoria (k-fold): filtra autocorrelación temporal.
