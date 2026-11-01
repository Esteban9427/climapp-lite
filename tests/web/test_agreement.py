"""Etiqueta visible según la confianza de un reporte verificado (TASK-017, ADR-002 §4).

"Verificado" solo dice que el texto pasó la compuerta; la etiqueta dice si los datos lo
respaldan. Umbrales SUPUESTO: ≥ 0,7 coincide, de 0,3 a 0,7 parcial, < 0,3 no coincide.
"""

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from climapp.config import Settings
from climapp.web.agreement import AgreementThresholds, agreement_label
from tests.api.test_reports_api import INSIDE, TEXT
from tests.conftest import rewrite_env
from tests.web.conftest import MakeClient

THRESHOLDS = AgreementThresholds(high=0.7, low=0.3)
HEADER = (
    "date,series_id,precip_mm,n_readings,valid,imputed,source_hash,n_suspect,suspect_mm,n_gap\n"
)


@pytest.mark.parametrize(
    ("score", "text", "css"),
    [
        (1.0, "Coincide con los datos", "badge-ok"),
        (0.7, "Coincide con los datos", "badge-ok"),
        (0.69, "Coincidencia parcial", "badge-partial"),
        (0.3, "Coincidencia parcial", "badge-partial"),
        (0.29, "No coincide con los datos", "badge-danger"),
        (0.0, "No coincide con los datos", "badge-danger"),
    ],
)
def test_label_depends_on_the_confidence(score: float, text: str, css: str) -> None:
    label = agreement_label(score, THRESHOLDS)
    assert (label.text, label.css) == (text, css)


def test_thresholds_come_from_settings_and_must_be_ordered(env_file: Path) -> None:
    settings = Settings(_env_file=env_file)
    assert AgreementThresholds.from_settings(settings) == THRESHOLDS
    rewrite_env(env_file, AGREEMENT_HIGH="0.3", AGREEMENT_LOW="0.7")
    with pytest.raises(ValidationError, match="AGREEMENT_LOW"):
        Settings(_env_file=env_file)


def _stations(settings: Settings, rows: dict[str, float]) -> None:
    lines = [f"2024-12-31,{s},{mm},144,true,false,h,0,0.0,0\n" for s, mm in rows.items()]
    (settings.data_dir / settings.daily_stations_file).write_text(HEADER + "".join(lines))


def _status_and_list(client: object) -> tuple[str, str]:
    partial = client.post("/web/reports", data={"text": TEXT, **INSIDE}).text  # type: ignore[attr-defined]
    poll = re.search(r'hx-get="(/web/reports/[0-9a-f-]+/estado)"', partial)
    assert poll
    return client.get(poll.group(1)).text, client.get("/").text  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("rows", "label", "pct"),
    [
        ({"EST-A": 30.0}, "Coincide con los datos", "100 %"),
        ({"EST-A": 30.0, "EST-D": 0.0}, "Coincidencia parcial", "50 %"),
        ({"EST-A": 0.0}, "No coincide con los datos", "0 %"),
    ],
)
def test_status_and_list_show_the_label_instead_of_a_bare_verified(
    make_client: MakeClient, web_settings: Settings, rows: dict[str, float], label: str, pct: str
) -> None:
    _stations(web_settings, rows)
    status, home = _status_and_list(make_client())
    for html in (status, home):
        assert f"{label} · confianza {pct}" in html
        assert "Verificado · confianza" not in html
    assert "Texto revisado por la compuerta" in status


def test_map_marker_label_says_whether_the_data_agree(
    make_client: MakeClient, web_settings: Settings
) -> None:
    _stations(web_settings, {"EST-A": 0.0})
    client = make_client()
    _status_and_list(client)
    html = client.get("/mapa", params={"replay_date": "2024-12-31"}).text
    assert "No coincide con los datos · confianza 0 %" in html
