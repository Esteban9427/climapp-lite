"""Tests del registro de periodos de falla conocidos (SP-13, ADR-004 §2). Datos sintéticos."""

import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from climapp.data.models import DailyPrecip
from climapp.data.outages import KnownOutage, apply_outages, load_known_outages
from tests.conftest import ROOT, env_example_items

RECORD = {
    "series_id": "EST-B",
    "desde": "2022-01-01",
    "hasta": "2022-01-03",
    "motivo": "falla del balancín",
    "fuente": "JM 2026-10-30",
}


def _write(path: Path, records: list[dict[str, str]]) -> Path:
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    return path


def _row(day: date, series: str = "EST-B", mm: float | None = 0.0) -> DailyPrecip:
    return DailyPrecip(
        date=day,
        series_id=series,
        precip_mm=mm,
        n_readings=144,
        valid=mm is not None,
        imputed=False,
        source_hash="h",
        n_suspect=0,
        suspect_mm=0.0,
        n_gap=0,
    )


def test_load_known_outages_reads_every_field(tmp_path: Path) -> None:
    (outage,) = load_known_outages(_write(tmp_path / "o.json", [RECORD]))
    assert outage == KnownOutage(
        series_id="EST-B",
        desde=date(2022, 1, 1),
        hasta=date(2022, 1, 3),
        motivo="falla del balancín",
        fuente="JM 2026-10-30",
    )


@pytest.mark.parametrize(
    "change",
    [
        {"series_id": "Estación real"},
        {"desde": "2022-01-04"},
        {"motivo": ""},
        {"fuente": " "},
    ],
)
def test_invalid_records_are_rejected(tmp_path: Path, change: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        load_known_outages(_write(tmp_path / "o.json", [RECORD | change]))


def test_missing_field_is_rejected(tmp_path: Path) -> None:
    record = {k: v for k, v in RECORD.items() if k != "fuente"}
    with pytest.raises(ValidationError):
        load_known_outages(_write(tmp_path / "o.json", [record]))


def test_apply_outages_invalidates_days_in_the_inclusive_period(tmp_path: Path) -> None:
    outages = load_known_outages(_write(tmp_path / "o.json", [RECORD]))
    days = [date(2021, 12, 31), date(2022, 1, 1), date(2022, 1, 3), date(2022, 1, 4)]
    rows = apply_outages([_row(d, mm=1.5) for d in days], outages)
    assert [r.valid for r in rows] == [True, False, False, True]
    assert [r.precip_mm for r in rows] == [1.5, None, None, 1.5]
    assert rows[1].n_readings == 144  # se conserva el conteo para auditoría


def test_apply_outages_leaves_other_series_untouched(tmp_path: Path) -> None:
    outages = load_known_outages(_write(tmp_path / "o.json", [RECORD]))
    row = _row(date(2022, 1, 2), series="EST-A", mm=3.0)
    assert apply_outages([row], outages) == [row]


def test_versioned_registry_is_valid_and_has_the_est_b_outage() -> None:
    path = ROOT / env_example_items()["KNOWN_OUTAGES_FILE"]
    outages = load_known_outages(path)
    est_b = [o for o in outages if o.series_id == "EST-B"]
    assert est_b[0].desde == date(2022, 1, 1)
    assert est_b[0].fuente == "JM 2026-10-30"
