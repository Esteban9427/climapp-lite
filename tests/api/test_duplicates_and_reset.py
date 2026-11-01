"""Duplicados y reinicio de la demo (revisión visual del 2026-11-01, TASK-016).

Un mismo texto enviado dos veces en menos de `DUPLICATE_WINDOW_MIN` (10 min) no crea un
reporte nuevo: se devuelve el anterior marcado `duplicate=true` y no se vuelve a pintar.
`climapp-demo-reset` vacía los reportes de la base local, con confirmación.
"""

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from climapp.api.main import create_app, get_now, get_settings
from climapp.api.reports import get_muse_client
from climapp.api.store import ReportStore
from climapp.config import Settings
from climapp.api.demo_reset import main as demo_reset
from climapp.verification.muse import MuseTask
from tests.api.contract import assert_matches
from tests.api.test_reports_api import INSIDE, SQUARE, STRUCTURED, TEXT, VERDICT
from tests.conftest import rewrite_env
from tests.verification.fakes import ScriptedMuse, reply

T0 = datetime(2026, 10, 2, 21, 30, tzinfo=UTC)


@pytest.fixture
def settings(env_file: Path) -> Settings:
    loaded = Settings(_env_file=env_file)
    path = loaded.data_dir / loaded.basin_polygon_file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"type": "Polygon", "coordinates": [SQUARE]}), encoding="utf-8")
    return loaded


class Clock:
    """Reloj que avanza a mano."""

    def __init__(self) -> None:
        self.now = T0


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def client(settings: Settings, clock: Clock) -> Iterator[TestClient]:
    muse = ScriptedMuse(
        {MuseTask.STRUCTURE: [reply(STRUCTURED)] * 5, MuseTask.JUDGE: [reply(VERDICT)] * 5}
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_muse_client] = lambda: muse
    app.dependency_overrides[get_now] = lambda: clock.now
    with TestClient(app) as test_client:
        yield test_client


def _store(settings: Settings) -> ReportStore:
    return ReportStore(settings.data_dir / settings.reports_db_file, settings.local_timezone)


def test_same_text_within_the_window_returns_the_first_report_as_duplicate(
    client: TestClient, settings: Settings, clock: Clock
) -> None:
    first = client.post("/reports", data={"text": TEXT, **INSIDE}).json()
    clock.now = T0 + timedelta(minutes=9)
    again = client.post("/reports", data={"text": f"  {TEXT.upper()} ", **INSIDE})
    assert_matches(again.json(), "Report")
    assert (again.json()["id"], again.json()["duplicate"]) == (first["id"], True)
    assert first["duplicate"] is False
    assert len(_store(settings).list(None, None, None, 10)) == 1


def test_same_text_after_the_window_is_a_new_report(
    client: TestClient, settings: Settings, clock: Clock
) -> None:
    first = client.post("/reports", data={"text": TEXT, **INSIDE}).json()
    clock.now = T0 + timedelta(minutes=11)
    later = client.post("/reports", data={"text": TEXT, **INSIDE}).json()
    assert later["id"] != first["id"] and later["duplicate"] is False
    assert len(_store(settings).list(None, None, None, 10)) == 2


def test_web_says_the_report_is_a_duplicate(client: TestClient) -> None:
    client.post("/web/reports", data={"text": TEXT, **INSIDE})
    html = client.post("/web/reports", data={"text": TEXT, **INSIDE}).text
    assert "Reporte duplicado: ya lo recibimos hace menos de 10 min" in html


# --- climapp-demo-reset -------------------------------------------------------------


def test_demo_reset_empties_the_reports_after_confirmation(
    client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.post("/reports", data={"text": TEXT, **INSIDE})
    monkeypatch.setattr("climapp.api.demo_reset.Settings", lambda: settings)
    assert demo_reset([], answer=lambda _: "BORRAR") == 0
    assert _store(settings).list(None, None, None, 10) == []


def test_demo_reset_without_confirmation_keeps_the_reports(
    client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.post("/reports", data={"text": TEXT, **INSIDE})
    monkeypatch.setattr("climapp.api.demo_reset.Settings", lambda: settings)
    assert demo_reset([], answer=lambda _: "no") == 1
    assert len(_store(settings).list(None, None, None, 10)) == 1


def test_demo_reset_with_yes_flag_does_not_ask(
    client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.post("/reports", data={"text": TEXT, **INSIDE})
    monkeypatch.setattr("climapp.api.demo_reset.Settings", lambda: settings)

    def never(_: str) -> str:
        raise AssertionError

    assert demo_reset(["--yes"], answer=never) == 0
    assert _store(settings).list(None, None, None, 10) == []


def test_duplicate_window_is_a_setting(env_file: Path) -> None:
    assert Settings(_env_file=env_file).duplicate_window_min == 10
    with pytest.raises(ValueError, match="duplicate_window_min"):
        Settings(_env_file=rewrite_env(env_file, DUPLICATE_WINDOW_MIN="0"))
