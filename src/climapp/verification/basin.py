"""Polígono de la cuenca: decide si un reporte está dentro (TASK-016).

El polígono vive en `BASIN_POLYGON_FILE` (GeoJSON, fuera de git). Se aceptan `Polygon` y
`MultiPolygon`, sueltos o dentro de un `Feature` o `FeatureCollection`. Coordenadas en
orden GeoJSON: `[lon, lat]`. Un punto en un hueco del polígono está fuera.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

Ring = tuple[tuple[float, float], ...]  # (lon, lat)
MIN_RING_POINTS = 4  # un anillo cerrado necesita al menos 3 vértices distintos + el cierre


class BasinError(Exception):
    """El polígono de la cuenca falta o no es válido."""


def _inside_ring(ring: Ring, lon: float, lat: float) -> bool:
    """Prueba del rayo (par-impar) para un anillo."""
    inside = False
    for (x1, y1), (x2, y2) in pairwise(ring):
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


@dataclass(frozen=True, slots=True)
class Basin:
    """Partes del polígono: cada una es (anillo exterior, huecos...)."""

    polygons: tuple[tuple[Ring, ...], ...]

    def contains(self, lat: float, lon: float) -> bool:
        """`True` si el punto cae dentro de alguna parte y fuera de sus huecos."""
        for outer, *holes in self.polygons:
            if _inside_ring(outer, lon, lat) and not any(_inside_ring(h, lon, lat) for h in holes):
                return True
        return False


def _ring(points: Sequence[Sequence[float]]) -> Ring:
    """Anillo validado."""
    ring = tuple((float(p[0]), float(p[1])) for p in points)
    if len(ring) < MIN_RING_POINTS:
        msg = "cada anillo del polígono necesita al menos 4 puntos"
        raise BasinError(msg)
    return ring


def _geometry(doc: dict[str, Any]) -> dict[str, Any]:
    """Geometría de un GeoJSON suelto, `Feature` o `FeatureCollection` (la primera).

    `Any`: frontera con un JSON externo; la estructura se valida al leer los anillos.
    """
    if doc.get("type") == "FeatureCollection":
        doc = doc["features"][0]
    if doc.get("type") == "Feature":
        doc = doc["geometry"]
    return doc


def load_basin(path: Path) -> Basin:
    """Lee el polígono de la cuenca.

    Raises:
        BasinError: si falta el archivo, no es JSON o la geometría no es un polígono válido.
    """
    try:
        geometry = _geometry(json.loads(path.read_text(encoding="utf-8")))
        kind, coords = geometry.get("type"), geometry.get("coordinates")
        parts: list[Any] | None = {"Polygon": [coords], "MultiPolygon": coords}.get(str(kind))
        if parts is None:
            msg = f"geometría no soportada: {kind}"
            raise BasinError(msg)
        return Basin(tuple(tuple(_ring(r) for r in part) for part in parts))
    except FileNotFoundError as err:
        msg = f"no existe BASIN_POLYGON_FILE ({path.name})"
        raise BasinError(msg) from err
    except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as err:
        msg = f"BASIN_POLYGON_FILE no es un GeoJSON válido: {type(err).__name__}"
        raise BasinError(msg) from err
