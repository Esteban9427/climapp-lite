"""Fixtures de las vistas: artefactos sintéticos en DATA_DIR y Muse falso (sin red)."""

import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from climapp.api.main import create_app, get_explainer, get_now, get_settings
from climapp.api.reports import get_muse_client
from climapp.config import Settings
from climapp.verification.muse import MuseClient, MuseTask
from tests.api.test_forecast_api import EVALUATION, FORECASTS
from tests.api.test_reports_api import SQUARE, STRUCTURED, VERDICT
from tests.conftest import rewrite_env
from tests.verification.fakes import ScriptedMuse, reply

OFFICIAL = "https://example.org/gestion-del-riesgo"
NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


@pytest.fixture
def web_settings(env_file: Path) -> Settings:
    rewrite_env(env_file, OFFICIAL_CHANNELS_URL=OFFICIAL)
    settings = Settings(_env_file=env_file)
    data = settings.data_dir
    (data / "derived").mkdir(parents=True)
    (data / settings.forecasts_file).write_text(json.dumps(FORECASTS), encoding="utf-8")
    (data / settings.evaluation_file).write_text(json.dumps(EVALUATION), encoding="utf-8")
    basin = {"type": "Polygon", "coordinates": [SQUARE]}
    (data / settings.basin_polygon_file).write_text(json.dumps(basin), encoding="utf-8")
    return settings


def verifying_muse() -> ScriptedMuse:
    return ScriptedMuse({MuseTask.STRUCTURE: [reply(STRUCTURED)], MuseTask.JUDGE: [reply(VERDICT)]})


MakeClient = Callable[..., TestClient]


@pytest.fixture
def make_client(web_settings: Settings) -> Iterator[MakeClient]:
    clients: list[TestClient] = []

    def make(muse: MuseClient | None = None, explainer: object = None) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: web_settings
        app.dependency_overrides[get_now] = lambda: NOW
        app.dependency_overrides[get_muse_client] = lambda: muse or verifying_muse()
        app.dependency_overrides[get_explainer] = lambda: explainer
        client = TestClient(app)
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.close()
