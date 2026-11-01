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
    # reproducción de la emisión 2024-12-30: el día objetivo es el 2024-12-31
    data = _map_data(client.get("/mapa", params={"replay_date": "2024-12-30"}).text)
    markers = data["markers"]
    assert isinstance(markers, list) and len(markers) == 1
    assert (markers[0]["lat"], markers[0]["lon"]) == (1.512, -1.499)
    assert markers[0]["label"].startswith("Lluvia fuerte · ") and "%" in markers[0]["label"]


def test_legend_shows_the_forecast_outcome_of_the_target_day(make_client: MakeClient) -> None:
    html = make_client().get("/mapa", params={"replay_date": "2024-12-31"}).text
    assert "Pronóstico para el 2025-01-01: falsa alarma" in html
    assert "Reproducción histórica" in html


def test_replay_shows_by_default_the_reports_of_the_target_day(make_client: MakeClient) -> None:
    html = make_client().get("/mapa", params={"replay_date": "2024-12-31"}).text
    assert "Reportes observados el 2025-01-01" in html
    assert "Pronóstico para el 2025-01-01: falsa alarma" in html


def test_live_map_shows_the_reports_of_today(make_client: MakeClient) -> None:
    assert "Reportes observados el 2026-10-23" in make_client().get("/mapa").text


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
    html = client.get("/mapa", params={"replay_date": "2024-12-30"}).text
    listing = re.search(r'<ul class="reports" id="map-list">(.*?)</ul>', html, re.S)
    assert listing and "Lluvia fuerte" in listing.group(1)


def test_popups_are_built_as_text_not_html() -> None:
    script = (Path(__file__).resolve().parents[2] / "src/climapp/web/static/map.js").read_text()
    assert "row.textContent = line" in script  # cada línea del popup es texto
    assert "bindPopup(m.label)" not in script


# --- revisión visual del 2026-11-01 ----------------------------------------------------


def test_map_draws_the_provisional_basin_outline_with_its_label(make_client: MakeClient) -> None:
    html = make_client().get("/mapa").text
    assert "zona aproximada de la cuenca (provisional)" in html
    outline = _map_data(html)["basin"]
    assert outline == [
        [[1.0, -2.0], [1.0, -1.0], [2.0, -1.0], [2.0, -2.0], [1.0, -2.0]]
    ]  # [lat, lon]


def test_popup_details_show_each_evidence_value(
    make_client: MakeClient, web_settings: Settings
) -> None:
    header = (
        "date,series_id,precip_mm,n_readings,valid,imputed,source_hash,n_suspect,suspect_mm,n_gap\n"
    )
    path = web_settings.data_dir / web_settings.daily_stations_file
    path.write_text(header + "2024-12-31,EST-A,30.0,144,true,false,h,0,0.0,0\n")
    client = make_client()
    client.post("/web/reports", data={"text": TEXT, **INSIDE})
    (marker,) = _map_data(client.get("/mapa", params={"replay_date": "2024-12-30"}).text)["markers"]
    assert any("EST-A: 30 mm" in d and d.endswith("✓") for d in marker["details"])


def test_map_frames_the_basin_and_builds_popups_as_text() -> None:
    root = Path(__file__).resolve().parents[2] / "src/climapp/web/static"
    script = (root / "map.js").read_text()
    assert "L.polygon(data.basin" in script and "fitBounds(outline.getBounds()" in script
    assert "innerHTML" not in script
    css = (root / "app.css").read_text()
    rule = re.search(r"\.leaflet-top, \.leaflet-bottom \{ z-index: (\d+);", css)
    aviso = re.search(r"\.aviso \{[^}]*z-index: (\d+);", css)
    assert rule and aviso and int(rule.group(1)) < int(aviso.group(1))  # bajo el aviso fijo
