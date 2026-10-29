# ADR-005: Stack y frontend

- **Estado:** Aceptado
- **Fecha:** 2026-10-29

## Contexto
Hay 4 días de sprint (30-oct a 2-nov) con un solo desarrollador a tiempo completo. Se necesita una web móvil ligera con el pronóstico, el formulario de reporte y un mapa, servida junto a la API.

## Decisión
- **Backend:** Python 3.12 con `uv`, FastAPI y Pydantic v2. Calidad: `pytest` + `pytest-cov`, `ruff` (lint + format) y `mypy --strict` en `src/`.
- **Modelo:** scikit-learn y pandas. Los artefactos del modelo se guardan en `DATA_DIR/models/` (fuera de git), versionados por hash de datos y parámetros.
- **Frontend:** HTML renderizado en el servidor con **Jinja2 + HTMX** y **Leaflet** para el mapa, con teselas de OpenStreetMap y la atribución que exige su licencia ODbL.
  - Sin paso de build ni Node.
  - Un solo proceso que despliega API y vistas juntos.
  - HTMX cubre el refresco del estado del reporte (`202` → sondeo) sin un framework de componentes.
  - Las vistas son mobile-first, desde 360 px de ancho.
- **Contenedor:** Podman (nunca Docker), solo si hace falta para la demo. `Containerfile` en la raíz.
- **Configuración:** variables de entorno (`.env`, ignorado); `.env.example` documenta todas las claves sin secretos.
- **Logging:** `structlog` en JSON. Sin `print`.

## Alternativas descartadas
- React con Vite: más control de la UI, pero añade toolchain, build y otro proceso. No compensa en 4 días.
- Streamlit: rápido de armar, pero difícil de hacer móvil y de separar de la API documentada en OpenAPI.

## Consecuencias
- Menos interactividad rica en la UI, aceptable para 3 vistas.
- Los tests de las vistas son tests HTTP de FastAPI (TestClient) sobre el HTML.
