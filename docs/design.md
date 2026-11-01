# Diseño UI — ClimApp Lite (FORGE:DESIGNER, 2026-10-31)

> Base para TASK-017 (pronóstico, formulario y lista) y TASK-018 (mapa). Stack: Jinja2 + HTMX + Leaflet, sin build (ADR-005). Mobile-first desde **360 px**. Sin marcas ni logos institucionales: los organismos oficiales se nombran solo con texto y enlace.

## Principios
1. **El aviso "No es una alerta oficial" siempre está a la vista.** Es una franja fija arriba, visible en todas las vistas y estados (también en error y en carga), con los enlaces a los canales oficiales (Gestión del Riesgo de Cali e IDEAM).
2. **Nunca se sugiere seguridad.** No se usan verdes de "todo bien" para el pronóstico, ni frases como "es seguro ir". El pronóstico usa el color neutro de información.
3. **La verificación se ve.** Cada reporte muestra su estado con texto, no solo con color, y la confianza viene con su desglose por fuente.
4. **La reproducción histórica se distingue de lo vigente** con una etiqueta "Reproducción histórica" de alto contraste.

## Tokens
Definidos en `src/climapp/web/static/tokens.css` como variables CSS. Un test (`tests/web/test_design_tokens.py`) lee ese archivo y recalcula los contrastes de la tabla: si alguien cambia un color y rompe AA, el test falla.

### Color
| Token | Valor | Uso |
|-------|-------|-----|
| `--color-bg` | `#FFFFFF` | Fondo de página |
| `--color-surface` | `#F2F5F8` | Tarjetas |
| `--color-text` | `#1B232C` | Texto principal |
| `--color-text-muted` | `#4B5866` | Texto secundario, fechas, notas |
| `--color-primary` | `#0A58A8` | Botón principal, enlaces, foco |
| `--color-on-primary` | `#FFFFFF` | Texto sobre el botón principal |
| `--color-border` | `#7B8794` | Bordes de campos (no texto: exige 3:1) |
| `--color-warning-bg` / `--color-warning-text` | `#FFF1CC` / `#5A3A00` | Franja del aviso |
| `--color-warning-border` | `#B07800` | Borde de la franja del aviso |
| `--color-info-bg` / `--color-info-text` | `#E4EEF9` / `#0A4F96` | Pronóstico, estado "verificando" |
| `--color-success-bg` / `--color-success-text` | `#E3F4E8` / `#17602D` | Estado "verificado" (solo reportes) |
| `--color-danger-bg` / `--color-danger-text` | `#FDE7E5` / `#A1231B` | Estado "rechazado", errores |
| `--color-review-bg` / `--color-review-text` | `#F3E8FA` / `#6B2C8F` | Estado "requiere revisión humana" |
| `--color-disabled-bg` / `--color-disabled-text` | `#E6EAEE` / `#5A6571` | Controles deshabilitados |
| `--color-replay-bg` / `--color-replay-text` | `#3D2C8D` / `#FFFFFF` | Etiqueta "Reproducción histórica" |

### Contraste WCAG 2.1 AA (verificado con la fórmula de luminancia relativa)
| Par | Contraste | Mínimo | Cumple |
|-----|-----------|--------|--------|
| Texto sobre fondo | 15,87 | 4,5 | Sí |
| Texto sobre tarjeta | 14,50 | 4,5 | Sí |
| Texto secundario sobre fondo | 7,27 | 4,5 | Sí |
| Texto secundario sobre tarjeta | 6,65 | 4,5 | Sí |
| Texto sobre botón principal | 7,06 | 4,5 | Sí |
| Enlace sobre fondo | 7,06 | 4,5 | Sí |
| Aviso: texto sobre su fondo | 9,17 | 4,5 | Sí |
| Aviso: borde sobre fondo | 3,80 | 3,0 (no texto) | Sí |
| Info / verificando | 6,96 | 4,5 | Sí |
| Verificado | 6,69 | 4,5 | Sí |
| Rechazado / error | 6,40 | 4,5 | Sí |
| Requiere revisión humana | 7,44 | 4,5 | Sí |
| Deshabilitado | 4,91 | 4,5 (AA no lo exige; se cumple igual) | Sí |
| Borde de campo sobre fondo | 3,66 | 3,0 (no texto) | Sí |
| Anillo de foco sobre fondo | 7,06 | 3,0 (no texto) | Sí |
| Reproducción histórica | 10,81 | 4,5 | Sí |

### Tipografía
- Familia: pila del sistema (`system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`); no se descargan fuentes, así carga rápido con mala señal.
- Escala (`rem`, base 16 px): `--font-size-sm` 0,875 · `--font-size-base` 1 · `--font-size-lg` 1,25 · `--font-size-xl` 1,5 · `--font-size-display` 2,25 (la probabilidad).
- Interlineado 1,5 en texto y 1,2 en títulos. Peso 400 normal y 700 para títulos y la cifra principal.
- El texto se puede ampliar al 200 % sin perder contenido (unidades `rem`, sin alturas fijas).

### Espaciado y forma
- Escala de 4 px: `--space-1` 4 · `--space-2` 8 · `--space-3` 12 · `--space-4` 16 · `--space-5` 24 · `--space-6` 32.
- Margen lateral de página: 16 px. Ancho máximo del contenido: 40 rem, centrado.
- Radio: `--radius` 8 px. Borde: 1 px en campos y 2 px en el aviso.
- Objetivos táctiles de **al menos 44 × 44 px**.
- Foco visible: contorno de 3 px `--color-primary` con 2 px de separación; nunca `outline: none`.

## Diseño a 360 px (una columna)
```
┌──────────────────────────────┐
│ ⚠ No es una alerta oficial…  │ ← aviso fijo (sticky), con enlaces Cali · IDEAM
├──────────────────────────────┤
│ [Reproducción histórica]     │ ← solo con replay_date
│ Mañana · 1 ene 2025          │
│   13 %                       │ ← probabilidad de ≥ 20 mm (display)
│ de llegar a 20 mm en la      │
│ cuenca (media de estaciones) │
│ Acumulado 3 días: 40,8 mm    │
│ Explicación verificada …     │
├──────────────────────────────┤
│ Reportar lo que ves          │
│ [ texto                    ] │
│ [ foto (opcional)          ] │
│ [Usar mi ubicación]          │
│ [ Enviar reporte ]           │
│ Estado: Verificando…         │ ← se actualiza solo (HTMX)
├──────────────────────────────┤
│ Reportes verificados         │
│ • lluvia fuerte · 72 %       │
│ Ver mapa →                   │
└──────────────────────────────┘
```
Desde 720 px, la tarjeta del pronóstico y el formulario van en dos columnas; el aviso sigue arriba a todo lo ancho.

## Componentes y estados
Todos los estados usan texto, además del color (WCAG 1.4.1). Las regiones que cambian solas llevan `aria-live="polite"`.

| Componente | Normal | Cargando | Error | Vacío | Deshabilitado | Verificando | Rechazado | Requiere revisión humana |
|------------|--------|----------|-------|-------|---------------|-------------|-----------|--------------------------|
| **Aviso** | Franja con texto y enlaces | Igual (se renderiza en el servidor, no depende de datos) | Igual | Igual | — | — | — | — |
| **Tarjeta de pronóstico** | Probabilidad, umbral, acumulado y variante | "Cargando pronóstico…" con borde punteado | "No hay pronóstico calculado" (503), fondo de error y el aviso visible | — | — | — | — | — |
| **Indicador de vigencia** | "Emitido hace N h" | — | — | — | — | — | — | — |
| **Etiqueta de reproducción** | "Reproducción histórica · emisión AAAA-MM-DD" | — | — | — | — | — | — | — |
| **Explicación** | Texto verificado + "Verificado por la compuerta" (+ "respuesta grabada" si `explanation_fallback`) | — | — | "Sin explicación verificada": nunca se muestra un texto que no pasó la compuerta | — | — | — | — |
| **Formulario de reporte** | Campos y botón principal | Botón "Enviando…" deshabilitado | Mensaje bajo el campo (p. ej. "La foto supera 5 MB") con `aria-describedby` | — | Botón con colores de deshabilitado mientras falta texto o foto, o ubicación | — | — | — |
| **Estado del reporte** | — | — | "No se pudo consultar el estado; reintenta" | — | — | Insignia info "Verificando…" y sondeo cada 2 s | Insignia de error "Rechazado: fuera de la cuenca" o el motivo | Insignia violeta "Requiere revisión humana", con los motivos de cada intento |
| **Insignia verificado** | Etiqueta según la confianza ("Coincide con los datos", "Coincidencia parcial" o "No coincide con los datos"), la confianza en %, el desglose por fuente y "Texto revisado por la compuerta de verificación" | — | — | — | — | — | — | — |
| **Lista de reportes** | Tarjetas con tipo, intensidad, hora y confianza | "Cargando reportes…" | "No se pudo cargar la lista" | "Aún no hay reportes verificados" | — | — | — | — |
| **Mapa** | Marcadores de reportes verificados y leyenda con el resultado del día | Contenedor gris con "Cargando mapa…" | "No se pudo cargar el mapa base"; los reportes siguen en la lista | "No hay reportes verificados para este día" en la leyenda | — | — | — | — |

### Textos de los estados de reporte
> **Etiqueta según la confianza (2026-11-01, SUPUESTO, ADR-002 §4):** `verificado` solo dice que el texto pasó la compuerta, así que nunca se muestra solo. Un reporte verificado con confianza baja no puede leerse como confirmado. Los umbrales (`AGREEMENT_HIGH` = 0,7 y `AGREEMENT_LOW` = 0,3) son un SUPUESTO del equipo; cada corte pertenece al tramo de arriba. Solo cambia la vista (lista, estado y mapa): el contrato de la API no cambia.

| Estado | Texto visible |
|--------|---------------|
| `verificando` | "Verificando tu reporte…" |
| `verificado`, confianza ≥ `AGREEMENT_HIGH` (0,7) | "Coincide con los datos · confianza N %" (insignia de éxito) |
| `verificado`, confianza ≥ `AGREEMENT_LOW` (0,3) y < 0,7 | "Coincidencia parcial · confianza N %" (insignia de advertencia) |
| `verificado`, confianza < `AGREEMENT_LOW` (0,3) | "No coincide con los datos · confianza N %" (insignia de error) |
| `rechazado` + `fuera_de_cuenca` | "Rechazado: la ubicación está fuera de la cuenca del río Pance" |
| `rechazado` + `entrada_invalida` | "Rechazado: revisa el texto o la foto" |
| `requiere_revision_humana` | "Requiere revisión humana: no pudimos verificarlo automáticamente" |

## Mapa (TASK-018)
- Leaflet con teselas de OpenStreetMap y la atribución obligatoria "© OpenStreetMap contributors" (ODbL), siempre visible.
- Solo se muestran los reportes **verificados**, con las coordenadas redondeadas a 3 decimales (~100 m).
- Leyenda: el resultado del pronóstico del día (`acierto`, `falsa_alarma`, `fallo` o `correcto_negativo`), con texto.
- Día de los reportes (2026-11-01): en vivo, los de hoy; en una reproducción (`replay_date` = día de emisión), **por defecto los del día objetivo**, que es el que evalúa la leyenda. La leyenda dice "Reportes observados el AAAA-MM-DD".
- Altura de 60 vh en móvil. Si el mapa base no carga, la lista de reportes sigue siendo la fuente accesible.

## Accesibilidad
- `lang="es"`, títulos en orden (`h1` único por vista) y etiquetas `<label>` en todos los campos.
- Las imágenes llevan `alt`; las insignias de estado son texto, no iconos solos.
- Se respeta `prefers-reduced-motion`: el sondeo no anima nada.
- Revisión manual a 360 px antes de cerrar TASK-017.
