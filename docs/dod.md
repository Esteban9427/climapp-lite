# Definición de Hecho (DoD) — ClimApp Lite

Una tarea está **hecha** solo si cumple todo lo siguiente:

1. **TDD**: el test se escribió antes que el código y quedó en el historial (rojo → verde).
2. `uv run pytest` en verde; cobertura ≥ 85 % en `core-paths.txt` y ≥ 70 % global, sin bajar respecto de `main`.
3. `uv run ruff check .`, `uv run ruff format --check .` y `uv run mypy src` sin errores.
4. Se cumplen las reglas de `CLAUDE.md`: sin `print`, sin `except Exception`, funciones ≤ 30 líneas, docstrings y tipado.
5. Ninguna cifra o umbral nuevo sin fuente o sin la marca SUPUESTO.
6. **Sin datos ni secretos** en el commit: `gitleaks detect` limpio y ningún archivo de `data/` ni `.env`.
7. **Sin nombres ni coordenadas de estaciones**: `git grep -niEf .forbidden-terms` devuelve 0 resultados. `.forbidden-terms` es local y no se versiona (un patrón por línea; lo entrega el equipo), porque listar los términos en el repo los publicaría.
8. Si toca el núcleo o el contrato de la API: revisión de Muse Code en solo lectura guardada en `docs/reviews/TASK-NNN.md` y atendida (ADR-003).
9. El contrato de la API coincide con `docs/openapi.yaml` (test de contrato).
10. Commit convencional en español, solo con las rutas de la tarea.
11. Línea agregada en "Construido durante el evento" del README.
12. La demo sigue funcionando con `DEMO_FALLBACK=1` al cerrar el día.
