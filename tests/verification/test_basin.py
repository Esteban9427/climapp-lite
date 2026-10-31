"""Tests del polígono de la cuenca (TASK-016). Geometría sintética, sin lugares reales."""

import json
from pathlib import Path

import pytest

from climapp.verification.basin import BasinError, load_basin

SQUARE = [[-2.0, 1.0], [-1.0, 1.0], [-1.0, 2.0], [-2.0, 2.0], [-2.0, 1.0]]  # [lon, lat]
HOLE = [[-1.6, 1.4], [-1.4, 1.4], [-1.4, 1.6], [-1.6, 1.6], [-1.6, 1.4]]


def _write(tmp_path: Path, geometry: dict[str, object], wrap: str = "Feature") -> Path:
    if wrap == "Feature":
        doc: dict[str, object] = {"type": "Feature", "properties": {}, "geometry": geometry}
    elif wrap == "FeatureCollection":
        doc = {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {}, "geometry": geometry}],
        }
    else:
        doc = geometry
    path = tmp_path / "basin.geojson"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


@pytest.mark.parametrize("wrap", ["Feature", "FeatureCollection", "Geometry"])
def test_point_inside_and_outside_a_polygon(tmp_path: Path, wrap: str) -> None:
    basin = load_basin(_write(tmp_path, {"type": "Polygon", "coordinates": [SQUARE]}, wrap))
    assert basin.contains(lat=1.5, lon=-1.5)
    assert not basin.contains(lat=2.5, lon=-1.5)
    assert not basin.contains(lat=1.5, lon=-0.5)


def test_point_in_a_hole_is_outside(tmp_path: Path) -> None:
    basin = load_basin(_write(tmp_path, {"type": "Polygon", "coordinates": [SQUARE, HOLE]}))
    assert not basin.contains(lat=1.5, lon=-1.5)
    assert basin.contains(lat=1.2, lon=-1.8)


def test_multipolygon_contains_points_of_any_part(tmp_path: Path) -> None:
    far = [[[10.0, 10.0], [11.0, 10.0], [11.0, 11.0], [10.0, 11.0], [10.0, 10.0]]]
    basin = load_basin(_write(tmp_path, {"type": "MultiPolygon", "coordinates": [[SQUARE], far]}))
    assert basin.contains(lat=1.5, lon=-1.5) and basin.contains(lat=10.5, lon=10.5)


def test_missing_file_is_a_basin_error(tmp_path: Path) -> None:
    with pytest.raises(BasinError, match="BASIN_POLYGON_FILE"):
        load_basin(tmp_path / "no.geojson")


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "Point", "coordinates": [-1.5, 1.5]},
        {"type": "Polygon", "coordinates": [[[0, 0], [1, 1]]]},
    ],
)
def test_unsupported_or_degenerate_geometry_is_rejected(
    tmp_path: Path, geometry: dict[str, object]
) -> None:
    with pytest.raises(BasinError):
        load_basin(_write(tmp_path, geometry))


def test_invalid_json_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "basin.geojson"
    path.write_text("{no json", encoding="utf-8")
    with pytest.raises(BasinError):
        load_basin(path)
