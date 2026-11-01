"""Reproducciones de la demo de punta a punta, sin red (TASK-019, US-06).

DEMO_FALLBACK=1 con las respuestas reales grabadas en `config/muse_fallback.json`. Los
artefactos del pronóstico replican las salidas del modelo para cada emisión (ya
publicadas en el PRD); la geometría, la lluvia de las estaciones y el nivel son sintéticos.

- Evento de la demo (2026-11-01): emisión 2026-10-01, objetivo 2026-10-02, acierto.
- E1 (2026-10-30): emisión 2024-12-31, objetivo 2025-01-01. Se conserva como caso de
  falsa alarma, con sus grabaciones del 2026-10-31.
"""

import json
import re
import socket
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from climapp.api.main import create_app, get_now, get_settings
from climapp.config import Settings
from climapp.web.demo import load_demo_reports
from tests.api.test_forecast_api import EVALUATION
from tests.api.test_reports_api import INSIDE, SQUARE
from tests.conftest import ROOT, env_example_items, rewrite_env
from tests.web.test_agreement import VERIFIED_LABEL

DEMO_REPORTS = load_demo_reports(ROOT / env_example_items()["DEMO_REPORTS_FILE"])
NOW = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)

DEMO_ISSUE, DEMO_TARGET = "2026-10-01", "2026-10-02"
DEMO_FORECASTS = [
    {
        "variant": variant,
        "issue_date": DEMO_ISSUE,
        "target_date": DEMO_TARGET,
        "issued_at": "2026-10-02T00:00:00-05:00",
        "prob_ge_threshold": prob,
        "accum_3d_mm": 93.7,
        "accum_3d_level": "normal",
        "inputs_available": ["EST-A", "EST-C"],
        "model_version": "c839469b8df2",
    }
    for variant, prob in (("historica", 0.1324200913242009), ("operativa", 0.14942528735632185))
]
DEMO_DAILY = {"date": DEMO_TARGET, "prob": 0.149, "observed": True, "outcome": "acierto"}

E1_ISSUE = "2024-12-31"
E1_TIME = "2024-12-31T16:30:00-05:00"
E1_TEXT = "Cae una llovizna suave en el sendero de la parte media; el río se ve normal."
E1_FORECASTS = [
    {
        "variant": "historica",
        "issue_date": E1_ISSUE,
        "target_date": "2025-01-01",
        "issued_at": "2025-01-01T00:00:00-05:00",
        "prob_ge_threshold": 0.1324200913242009,
        "accum_3d_mm": 40.8,
        "accum_3d_level": "normal",
        "inputs_available": ["CHIRPS", "EST-A", "EST-B", "EST-C", "EST-D"],
        "model_version": "c839469b8df2",
    }
]

# Evidencia sintética del día objetivo: llovió en las dos estaciones y el río subió
STATIONS_CSV = (
    "date,series_id,precip_mm,n_readings,valid,imputed,source_hash,n_suspect,suspect_mm,n_gap\n"
    f"{DEMO_TARGET},EST-A,30.0,144,true,false,h,0,0.0,0\n"
    f"{DEMO_TARGET},EST-C,25.0,144,true,false,h,0,0.0,0\n"
)
LEVEL_CSV = (
    "series_id,date,n_readings,level_min_m,level_max_m,rise_24h_max_m\n"
    f"EST-A,{DEMO_TARGET},144,0.40,0.90,0.50\n"
)

MakeDemo = Callable[..., TestClient]


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cualquier conexión de red falla: la demo tiene que correr sin ella."""

    def _refuse(*_: object, **__: object) -> None:
        msg = "red bloqueada en la demo"
        raise OSError(msg)

    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)


def _write_artifacts(
    settings: Settings, forecasts: list[dict[str, Any]], daily: dict[str, Any]
) -> None:
    data = settings.data_dir
    (data / "derived").mkdir(parents=True)
    evaluation = EVALUATION | {"daily": [daily]}
    (data / settings.forecasts_file).write_text(json.dumps(forecasts), encoding="utf-8")
    (data / settings.evaluation_file).write_text(json.dumps(evaluation), encoding="utf-8")
    basin = {"type": "Polygon", "coordinates": [SQUARE]}
    (data / settings.basin_polygon_file).write_text(json.dumps(basin), encoding="utf-8")
    (data / settings.daily_stations_file).write_text(STATIONS_CSV, encoding="utf-8")
    (data / settings.level_daily_file).write_text(LEVEL_CSV, encoding="utf-8")
    groups = {"groups": [["EST-A"], ["EST-B", "EST-C"]]}
    (data / settings.station_groups_file).write_text(json.dumps(groups), encoding="utf-8")


@pytest.fixture
def make_demo(env_file: Path, no_network: None) -> Iterator[MakeDemo]:
    clients: list[TestClient] = []

    def _make(forecasts: list[dict[str, Any]], daily: dict[str, Any], **env: str) -> TestClient:
        fallback = ROOT / env_example_items()["MUSE_FALLBACK_FILE"]
        rewrite_env(
            env_file, DEMO_FALLBACK="1", MUSE_FALLBACK_FILE=str(fallback), META_API_KEY="", **env
        )
        settings = Settings(_env_file=env_file)
        _write_artifacts(settings, forecasts, daily)
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_now] = lambda: NOW
        client = TestClient(app).__enter__()
        clients.append(client)
        return client

    yield _make
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def demo(make_demo: MakeDemo) -> TestClient:
    """El evento de la demo con la configuración de `.env.example`."""
    return make_demo(DEMO_FORECASTS, DEMO_DAILY)


@pytest.fixture
def e1(make_demo: MakeDemo) -> TestClient:
    """E1 con su fecha y su hora de reporte grabadas."""
    e1_daily = {"date": "2025-01-01", "prob": 0.11, "observed": False, "outcome": "falsa_alarma"}
    return make_demo(E1_FORECASTS, e1_daily, DEMO_REPLAY_DATE=E1_ISSUE, DEMO_REPORT_TIME=E1_TIME)


def _report(client: TestClient, text: str) -> tuple[str, dict[str, Any]]:
    """Envía un reporte desde la web y devuelve el estado mostrado y el detalle."""
    partial = client.post("/web/reports", data={"text": text, **INSIDE}).text
    poll = re.search(r'hx-get="/web/reports/([0-9a-f-]+)/estado"', partial)
    assert poll
    status = client.get(f"/web/reports/{poll.group(1)}/estado").text
    return status, client.get(f"/reports/{poll.group(1)}").json()


# --- evento de la demo: emisión 2026-10-01 -----------------------------------------


def test_the_demo_replays_the_2026_10_01_issue() -> None:
    items = env_example_items()
    assert items["DEMO_REPLAY_DATE"] == DEMO_ISSUE
    assert items["DEMO_REPORT_TIME"] == "2026-10-02T16:30:00-05:00"


def test_demo_examples_are_three_and_marked_as_simulated() -> None:
    assert len(DEMO_REPORTS) == 3
    for example in DEMO_REPORTS:
        assert example.titulo.startswith("Simulado")
        assert example.text.startswith("Reporte simulado")


def test_home_links_to_the_demo_replay(demo: TestClient) -> None:
    html = demo.get("/").text
    assert f'href="/?replay_date={DEMO_ISSUE}"' in html
    assert "Ver la reproducción histórica" in html


def test_demo_replay_end_to_end_without_network(demo: TestClient) -> None:
    home = demo.get(f"/?replay_date={DEMO_ISSUE}").text
    assert "Reproducción histórica" in home and "No es una alerta oficial" in home
    assert "13 %" in home
    assert re.search(r"Explicación</h2>\s*<p>[^<]*\b13 %", home)  # explicación real grabada
    assert "respuesta grabada" in home

    api = demo.get("/forecast", params={"replay_date": DEMO_ISSUE}).json()
    assert (api["replay"], api["variant"], api["explanation_fallback"]) == (True, "historica", True)

    mapa = demo.get("/mapa", params={"replay_date": DEMO_ISSUE}).text
    assert f"Pronóstico para el {DEMO_TARGET}: acierto" in mapa


def test_every_demo_example_has_an_exact_recording(demo: TestClient) -> None:
    for example in DEMO_REPORTS:
        status, detail = _report(demo, example.text)
        assert "sin grabación" not in status, example.titulo
        assert detail["review_reason"] != "sin_grabacion", example.titulo
        assert detail["attempts"], example.titulo


def test_the_exaggerated_report_goes_to_human_review_as_in_the_real_run(
    demo: TestClient,
) -> None:
    """En la corrida real (2026-11-01) el juez no encontró respaldo en el texto para lo
    que Muse estructuró, en los 3 intentos: la compuerta lo manda a revisión humana."""
    _, exaggerated, _ = DEMO_REPORTS
    status, detail = _report(demo, exaggerated.text)
    assert "Requiere revisión humana" in status
    assert (detail["status"], detail["structured"]) == ("requiere_revision_humana", None)
    assert len(detail["attempts"]) == 3


def test_the_true_report_is_backed_by_the_river_level(demo: TestClient) -> None:
    true_report, _, false_report = DEMO_REPORTS
    status, detail = _report(demo, true_report.text)
    assert detail["status"] == "verificado"
    assert "Coincide con los datos · confianza 100 %" in status
    assert detail["structured"]["event_type"] == "crecida"
    level = [s for s in detail["confidence"]["sources"] if s["kind"] == "river_level"]
    assert [s["agrees"] for s in level] == [True]

    dry_status, dry = _report(demo, false_report.text)
    assert dry["structured"]["event_type"] == "sin_lluvia"
    assert "No coincide con los datos · confianza 0 %" in dry_status  # verificado, pero falso
    assert dry["confidence"]["score"] < detail["confidence"]["score"]


def test_the_map_shows_the_demo_reports_of_the_target_day(demo: TestClient) -> None:
    for example in DEMO_REPORTS:
        _report(demo, example.text)
    # En la reproducción, el mapa muestra por defecto los reportes del día objetivo (10-02)
    mapa = demo.get("/mapa", params={"replay_date": DEMO_ISSUE}).text
    assert f"Reportes observados el {DEMO_TARGET}: 2" in mapa
    data = json.loads(re.search(r'id="map-data">(.*?)</script>', mapa, re.S).group(1))  # type: ignore[union-attr]
    assert len(data["markers"]) == 2  # el verdadero y el falso; el exagerado no se verificó


# --- E1: caso de falsa alarma, se conserva ------------------------------------------


def test_e1_replay_is_kept_as_a_false_alarm(e1: TestClient) -> None:
    home = e1.get(f"/?replay_date={E1_ISSUE}").text
    assert re.search(r"Explicación</h2>\s*<p>[^<]*\b13 %", home)
    assert "respuesta grabada" in home

    status, report = _report(e1, E1_TEXT)
    assert re.search(VERIFIED_LABEL, status)
    assert report["fallback"] is True and report["status"] == "verificado"

    mapa = e1.get("/mapa", params={"replay_date": E1_ISSUE}).text
    assert "Pronóstico para el 2025-01-01: falsa alarma" in mapa


def test_a_text_without_recording_fails_closed_in_the_demo(demo: TestClient) -> None:
    status, detail = _report(demo, "Este texto no está grabado")
    assert "Requiere revisión humana" in status and "sin grabación" in status
    assert detail["structured"] is None and detail["review_reason"] == "sin_grabacion"
