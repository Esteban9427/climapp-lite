# ClimApp Lite

ClimApp Lite publica cada día la probabilidad de que mañana caiga lluvia de 20 mm o más en la cuenca del río Pance (Cali, Colombia), junto con un indicador de lluvia acumulada en 3 días como señal de riesgo de derrumbe. Está pensada para el ciudadano o turista que decide si va al río. Quienes están en la zona pueden confirmar lo que ven con texto o foto, como un "Waze del clima". Muse Spark estructura cada reporte y explica el pronóstico en lenguaje claro, y la confianza de cada confirmación la calcula código verificable, no el modelo.

> **⚠️ No es una alerta oficial.** ClimApp Lite es un proyecto experimental. Ante cualquier riesgo, sigue las indicaciones de los organismos oficiales de gestión del riesgo y de meteorología.

## Tema
**Build for Your World**: aplicamos los modelos de Meta al dominio hidroclimático que conocemos, en una cuenca concreta.

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
- [ ] Pronóstico (random forest) evaluado contra climatología y persistencia.
- [ ] Compuerta de verificación de reportes con Muse Spark.
- [ ] Web móvil con pronóstico, reportes y mapa.

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
Ver [docs/data-sources.md](docs/data-sources.md). Los datos crudos no se versionan.

## Licencia
[MIT](LICENSE)
