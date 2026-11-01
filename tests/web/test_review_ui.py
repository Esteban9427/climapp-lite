"""Ajustes de la revisión visual en el celular (2026-11-01, TASK-017). Datos sintéticos.

Pronóstico con contexto (riesgo, climatología, percentil, variante histórica como línea
secundaria), formato es-CO, resultado bien visible de cada reporte con su desglose de
evidencia, ubicación de los ejemplos sobre el cauce y mensaje si falla la ubicación.
"""

import json
import re

from climapp.api.main import get_settings
from climapp.config import Settings
from climapp.verification.muse import MuseTask
from climapp.web.report_view import event_title
from tests.api.test_reports_api import CLAIMS, INSIDE, TEXT, VERDICT
from tests.conftest import ROOT
from tests.verification.fakes import ScriptedMuse, reply
from tests.web.conftest import MakeClient

HEADER = (
    "date,series_id,precip_mm,n_readings,valid,imputed,source_hash,n_suspect,suspect_mm,n_gap\n"
)


def _daily(settings: Settings, lines: list[str]) -> None:
    (settings.data_dir / settings.daily_stations_file).write_text(HEADER + "".join(lines))


def _training(settings: Settings) -> None:
    """Enero de 2014 en el entrenamiento: 3 de 16 días cerca del 1-ene con ≥ 20 mm."""
    rows = [
        f"2014-01-{d:02d},EST-A,{25.0 if d % 5 == 0 else 10.0},144,true,false,h,0,0.0,0\n"
        for d in range(1, 31)
    ]
    _daily(settings, rows)


# --- tarjeta del pronóstico --------------------------------------------------------


def test_replay_shows_the_operational_variant_with_risk_and_the_historical_as_secondary(
    make_client: MakeClient,
) -> None:
    html = make_client().get("/?replay_date=2024-12-31").text
    assert '<p class="prob">11 %</p>' in html
    assert "Riesgo elevado" in html  # 0,11 ≥ umbral de aviso 0,11 de la operativa
    assert "variante operativa" in html
    assert re.search(r"Variante histórica[^<]*: 15 %", html)
    assert "historica" not in html.replace("variant=historica", "")


def test_live_forecast_has_no_historical_line(make_client: MakeClient) -> None:
    assert "Variante histórica" not in make_client().get("/").text


def test_accumulation_shows_its_percentile_instead_of_normal(
    make_client: MakeClient, web_settings: Settings
) -> None:
    _training(web_settings)
    html = make_client().get("/?replay_date=2024-12-31").text
    assert "50,4 mm: más que el 100 % de los días del entrenamiento" in html
    assert "(normal)" not in html and "50.4" not in html
    assert "lo normal para esta época: 19 %" in html  # 3/16 = 18,75 %


# --- resultado del reporte y desglose de evidencia ---------------------------------


def _status(client: object, text: str = TEXT) -> str:
    partial = client.post("/web/reports", data={"text": text, **INSIDE}).text  # type: ignore[attr-defined]
    poll = re.search(r'hx-get="(/web/reports/[0-9a-f-]+/estado)"', partial)
    assert poll
    return client.get(poll.group(1)).text  # type: ignore[attr-defined]


def test_verified_report_shows_the_result_why_and_the_evidence_values(
    make_client: MakeClient, web_settings: Settings
) -> None:
    _daily(web_settings, ["2024-12-31,EST-A,30.0,144,true,false,h,0,0.0,0\n"])
    path = web_settings.data_dir / web_settings.imerg_early_file
    path.write_text("date,precip_mm\n2024-12-31,0.4\n", encoding="utf-8")
    html = _status(make_client())
    assert "Lluvia fuerte" in html
    assert "Coincidencia parcial" in html
    assert "Lo respaldan 1 de 2 fuentes con dato" in html
    assert re.search(r"Lluvia en estaciones[^<]*EST-A: 30 mm[^<]*✓", html)
    assert re.search(r"Satélite IMERG Early[^<]*0,4 mm[^<]*✗", html)
    assert "peso" not in html


def test_flood_report_shows_the_level_rise(make_client: MakeClient, web_settings: Settings) -> None:
    level = "series_id,date,n_readings,level_min_m,level_max_m,rise_24h_max_m\n"
    level += "EST-A,2024-12-31,144,0.40,1.08,0.68\n"
    (web_settings.data_dir / web_settings.level_daily_file).write_text(level)
    flood = json.dumps(
        {
            "event_type": "crecida",
            "intensity": "fuerte",
            "observed_at": "2024-12-31T16:30:00-05:00",
            "claims": CLAIMS,
            "numbers_cited": [],
        }
    )
    muse = ScriptedMuse({MuseTask.STRUCTURE: [reply(flood)], MuseTask.JUDGE: [reply(VERDICT)]})
    html = _status(make_client(muse))
    assert "Crecida fuerte" in html
    assert re.search(r"Nivel del río[^<]*subida de 0,68 m en 24 h[^<]*✓", html)


def test_report_in_human_review_says_so_and_why(make_client: MakeClient) -> None:
    rejected = json.dumps(
        {"claims": [{"text": c, "evidence": "", "supported": False} for c in CLAIMS]}
    )
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
            ]
            * 3,
            MuseTask.JUDGE: [reply(rejected)] * 3,
        }
    )
    html = _status(make_client(muse))
    assert "En revisión humana (no pasó la verificación tras 3 intentos)" in html
    assert "el verificador no encontró respaldo en el texto" in html


# --- ubicación de los ejemplos y de la persona -------------------------------------


def test_demo_examples_use_the_river_point_from_the_settings(
    make_client: MakeClient, web_settings: Settings
) -> None:
    demo = web_settings.model_copy(update={"demo_fallback": True})
    client = make_client()
    client.app.dependency_overrides[get_settings] = lambda: demo  # type: ignore[attr-defined]
    html = client.get("/").text
    lat, lon = demo.demo_example_lat, demo.demo_example_lon
    assert f'data-lat="{lat}"' in html and f'data-lon="{lon}"' in html
    assert "Ubicación de ejemplo: cauce del río Pance, parte media" in (
        ROOT / "src/climapp/web/static/app.js"
    ).read_text(encoding="utf-8")


def test_location_failure_explains_the_secure_context_and_the_demo_buttons() -> None:
    script = (ROOT / "src/climapp/web/static/app.js").read_text(encoding="utf-8")
    assert "window.isSecureContext" in script
    assert "conexión segura (https)" in script
    assert "usa los botones de ejemplo" in script


def test_settings_have_the_demo_example_point_with_its_source() -> None:
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "DEMO_EXAMPLE_LAT=" in env and "DEMO_EXAMPLE_LON=" in env
    assert "OpenStreetMap" in env and "ODbL" in env


def test_event_title_without_structured_fields_is_generic() -> None:
    """Un resumen sin tipo ni intensidad (mypy en 9c9572d) no rompe el título."""
    assert event_title(None, None) == "Reporte"
    assert event_title("crecida", "fuerte") == "Crecida fuerte"
    assert event_title("sin_lluvia", "ninguna") == "Sin lluvia"
