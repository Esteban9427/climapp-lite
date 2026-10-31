"""Reproducción de E1 de punta a punta, sin red (TASK-019, US-06).

DEMO_FALLBACK=1 con las respuestas reales grabadas en `config/muse_fallback.json`. Los
artefactos del pronóstico replican las salidas del modelo para la emisión 2024-12-31 (ya
publicadas en el PRD); la geometría es sintética.
"""

import json
import re
import socket
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from climapp.api.main import create_app, get_now, get_settings
from climapp.config import Settings
from tests.api.test_forecast_api import EVALUATION
from tests.api.test_reports_api import INSIDE, SQUARE
from tests.conftest import ROOT, env_example_items, rewrite_env

DEMO_TEXT = json.loads((ROOT / "config/demo_reports.json").read_text(encoding="utf-8"))[0]["text"]
E1_FORECAST = {
    "variant": "historica",
    "issue_date": "2024-12-31",
    "target_date": "2025-01-01",
    "issued_at": "2025-01-01T00:00:00-05:00",
    "prob_ge_threshold": 0.1324200913242009,
    "accum_3d_mm": 40.8,
    "accum_3d_level": "normal",
    "inputs_available": ["CHIRPS", "EST-A", "EST-B", "EST-C", "EST-D"],
    "model_version": "c839469b8df2",
}
NOW = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cualquier conexión de red falla: la demo tiene que correr sin ella."""

    def _refuse(*_: object, **__: object) -> None:
        msg = "red bloqueada en la demo"
        raise OSError(msg)

    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)


@pytest.fixture
def demo(env_file: Path, no_network: None) -> Iterator[TestClient]:
    fallback = ROOT / env_example_items()["MUSE_FALLBACK_FILE"]
    rewrite_env(
        env_file,
        DEMO_FALLBACK="1",
        MUSE_FALLBACK_FILE=str(fallback),
        DEMO_REPLAY_DATE="2024-12-31",
        META_API_KEY="",
    )
    settings = Settings(_env_file=env_file)
    data = settings.data_dir
    (data / "derived").mkdir(parents=True)
    (data / settings.forecasts_file).write_text(json.dumps([E1_FORECAST]), encoding="utf-8")
    (data / settings.evaluation_file).write_text(json.dumps(EVALUATION), encoding="utf-8")
    basin = {"type": "Polygon", "coordinates": [SQUARE]}
    (data / settings.basin_polygon_file).write_text(json.dumps(basin), encoding="utf-8")
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_now] = lambda: NOW
    with TestClient(app) as client:
        yield client


def test_home_links_to_the_e1_replay(demo: TestClient) -> None:
    html = demo.get("/").text
    assert 'href="/?replay_date=2024-12-31"' in html
    assert "Ver la reproducción histórica" in html


def test_e1_replay_end_to_end_without_network(demo: TestClient) -> None:
    home = demo.get("/?replay_date=2024-12-31").text
    assert "Reproducción histórica" in home and "No es una alerta oficial" in home
    assert "13 %" in home
    assert re.search(r"un 13 % de probabilidad", home)  # explicación real grabada
    assert "respuesta grabada" in home

    api = demo.get("/forecast", params={"replay_date": "2024-12-31"}).json()
    assert (api["replay"], api["variant"], api["explanation_fallback"]) == (True, "historica", True)

    partial = demo.post("/web/reports", data={"text": DEMO_TEXT, **INSIDE}).text
    poll = re.search(r'hx-get="/web/reports/([0-9a-f-]+)/estado"', partial)
    assert poll
    status = demo.get(f"/web/reports/{poll.group(1)}/estado").text
    assert re.search(r"Verificado · confianza \d+ %", status)
    assert "Respuesta grabada (demo)" in status
    report = demo.get(f"/reports/{poll.group(1)}").json()
    assert report["fallback"] is True and report["status"] == "verificado"

    mapa = demo.get("/mapa", params={"replay_date": "2024-12-31"}).text
    assert "Pronóstico para el 2025-01-01: falsa alarma" in mapa
    data = json.loads(re.search(r'id="map-data">(.*?)</script>', mapa, re.S).group(1))  # type: ignore[union-attr]
    assert len(data["markers"]) == 1  # el reporte grabado se observó el 2024-12-31


def test_a_text_without_recording_fails_closed_in_the_demo(demo: TestClient) -> None:
    form = {"text": "Este texto no está grabado", **INSIDE}
    partial = demo.post("/web/reports", data=form).text
    poll = re.search(r'hx-get="/web/reports/([0-9a-f-]+)/estado"', partial)
    assert poll
    status = demo.get(f"/web/reports/{poll.group(1)}/estado").text
    assert "Requiere revisión humana" in status and "sin grabación" in status
    detail = demo.get(f"/reports/{poll.group(1)}").json()
    assert detail["structured"] is None and detail["review_reason"] == "sin_grabacion"
