"""Tests del mapa mínimo: atribución OSM, marcadores del día y leyenda (TASK-018)."""

import json
import re
from pathlib import Path

from climapp.config import Settings
from climapp.verification.muse import MuseTask
from tests.api.test_reports_api import CLAIMS, INSIDE, OUTSIDE, TEXT, VERDICT
from tests.verification.fakes import ScriptedMuse, reply
from tests.web.conftest import MakeClient

OTHER_DAY = json.dumps(
    {
        "event_type": "lluvia",
        "intensity": "debil",
        "observed_at": "2024-12-20T10:00:00-05:00",
        "claims": CLAIMS,
        "numbers_cited": [],
    }
)


def _map_data(html: str) -> dict[str, object]:
    found = re.search(r'<script type="application/json" id="map-data">(.*?)</script>', html, re.S)
    assert found
    data: dict[str, object] = json.loads(found.group(1))
    return data


def test_map_page_includes_leaflet_and_the_visible_osm_attribution(make_client: MakeClient) -> None:
    html = make_client().get("/mapa").text
    assert (
        "/static/vendor/leaflet/leaflet.js" in html and "/static/vendor/leaflet/leaflet.css" in html
    )
    assert "© OpenStreetMap contributors" in html
    assert "https://www.openstreetmap.org/copyright" in html
    assert "No es una alerta oficial" in html
    data = _map_data(html)
    assert data["tile_url"] == "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    assert "OpenStreetMap" in str(data["attribution"])


def test_markers_are_the_verified_reports_observed_that_day(make_client: MakeClient) -> None:
    muse = ScriptedMuse(
        {
            MuseTask.STRUCTURE: [
                reply(
                    json.dumps(
                        {
                            "event_type": "lluvia",
                            "intensity": "fuerte",
                            "observed_at": "2024-12-31T16:30:00-05:00",
                            "claims": CLAIMS,
                            "numbers_cited": [],
                        }
                    )
                ),
                reply(OTHER_DAY),
            ],
            MuseTask.JUDGE: [reply(VERDICT), reply(VERDICT)],
        }
    )
    client = make_client(muse)
    client.post("/web/reports", data={"text": TEXT, **INSIDE})
    client.post("/web/reports", data={"text": TEXT, **INSIDE})  # observado otro día
    client.post("/web/reports", data={"text": TEXT, **OUTSIDE})  # rechazado: no va al mapa
    data = _map_data(client.get("/mapa", params={"replay_date": "2024-12-31"}).text)
    markers = data["markers"]
    assert isinstance(markers, list) and len(markers) == 1
    assert (markers[0]["lat"], markers[0]["lon"]) == (1.512, -1.499)
    assert "lluvia" in markers[0]["label"] and "%" in markers[0]["label"]


def test_legend_shows_the_forecast_outcome_of_the_target_day(make_client: MakeClient) -> None:
    html = make_client().get("/mapa", params={"replay_date": "2024-12-31"}).text
    assert "Pronóstico para el 2025-01-01: falsa alarma" in html
    assert "Reproducción histórica" in html


def test_day_without_reports_says_so_in_the_legend(make_client: MakeClient) -> None:
    html = make_client().get("/mapa", params={"replay_date": "2024-12-31"}).text
    assert "No hay reportes verificados para este día" in html
    assert _map_data(html)["markers"] == []


def test_map_centers_on_the_basin_when_there_are_no_markers(make_client: MakeClient) -> None:
    data = _map_data(make_client().get("/mapa").text)
    assert data["center"] == [1.5, -1.5]  # centro del polígono sintético


def test_live_map_without_outcome_says_it_is_not_evaluated_yet(make_client: MakeClient) -> None:
    html = make_client().get("/mapa").text
    assert "aún sin resultado observado" in html


def test_without_evaluation_or_polygon_the_map_still_renders(
    make_client: MakeClient, web_settings: Settings
) -> None:
    (web_settings.data_dir / web_settings.evaluation_file).unlink()
    (web_settings.data_dir / web_settings.basin_polygon_file).unlink()
    html = make_client().get("/mapa", params={"replay_date": "2024-12-31"}).text
    assert "aún sin resultado observado" in html
    assert _map_data(html)["center"] is None


def test_map_page_lists_the_markers_as_accessible_text(make_client: MakeClient) -> None:
    """Respaldo de docs/design.md: si el mapa base no carga, los reportes siguen en una lista."""
    muse = ScriptedMuse(
        {
            MuseTask.STRUCTURE: [
                reply(
                    json.dumps(
                        {
                            "event_type": "lluvia",
                            "intensity": "fuerte",
                            "observed_at": "2024-12-31T16:30:00-05:00",
                            "claims": CLAIMS,
                            "numbers_cited": [],
                        }
                    )
                )
            ],
            MuseTask.JUDGE: [reply(VERDICT)],
        }
    )
    client = make_client(muse)
    client.post("/web/reports", data={"text": TEXT, **INSIDE})
    html = client.get("/mapa", params={"replay_date": "2024-12-31"}).text
    listing = re.search(r'<ul class="reports" id="map-list">(.*?)</ul>', html, re.S)
    assert listing and "lluvia fuerte" in listing.group(1)


def test_popups_are_built_as_text_not_html() -> None:
    script = (Path(__file__).resolve().parents[2] / "src/climapp/web/static/map.js").read_text()
    assert "textContent = m.label" in script
    assert "bindPopup(m.label)" not in script
