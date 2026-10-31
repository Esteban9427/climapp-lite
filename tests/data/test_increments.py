"""Tests de la exportación de incrementos limpios cada 10 min (datos sintéticos)."""

import csv
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from climapp.data.increments import build_station_increments, write_increments_csv

from climapp.data.models import Reading, StepFlag
from tests.data.test_daily import CONFIG, MIDNIGHT, STEP, TZ, _write_export


def _export(tmp_path: Path) -> Path:
    values = [10.0, 10.2, 10.2, 5.0, 5.4]  # 00:00 … 00:40: lluvia, calma, reinicio, lluvia
    readings = [Reading("raw-a", "P", MIDNIGHT + i * STEP, v) for i, v in enumerate(values)]
    readings.append(Reading("raw-a", "P", MIDNIGHT + timedelta(days=1), 5.4))  # 00:00 siguiente
    return _write_export(tmp_path / "e.csv", readings)


def test_increments_use_the_same_cleaning_and_public_ids(tmp_path: Path) -> None:
    rows = build_station_increments([_export(tmp_path)], {"raw-a": "EST-A"}, CONFIG)
    assert {r.series_id for r in rows} == {"EST-A"}
    flags = [r.increment.flag for r in rows]
    assert flags[:4] == [StepFlag.OK, StepFlag.OK, StepFlag.RESET, StepFlag.OK]
    assert flags[4] is StepFlag.GAP  # hueco que cruza la medianoche
    assert [round(r.increment.mm, 1) for r in rows[:4]] == [0.2, 0.0, 0.0, 0.4]


def test_unmapped_station_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="sin correspondencia"):
        build_station_increments([_export(tmp_path)], {}, CONFIG)


def test_csv_has_local_time_local_day_mm_and_flag(tmp_path: Path) -> None:
    rows = build_station_increments([_export(tmp_path)], {"raw-a": "EST-A"}, CONFIG)
    out = write_increments_csv(rows, tmp_path / "out" / "inc.csv")
    records = list(csv.DictReader(out.open(encoding="utf-8")))
    assert list(records[0]) == ["series_id", "fecha_hora_local", "dia_local", "mm", "flag"]
    assert records[0] == {
        "series_id": "EST-A",
        "fecha_hora_local": "2024-12-31 00:10",
        "dia_local": "2024-12-31",
        "mm": "0.2",
        "flag": "ok",
    }
    last = records[-1]  # la lectura de las 00:00 cierra el día anterior
    assert (last["fecha_hora_local"], last["dia_local"], last["flag"]) == (
        "2025-01-01 00:00",
        "2024-12-31",
        "gap",
    )


def test_timestamps_are_written_in_local_time(tmp_path: Path) -> None:
    rows = build_station_increments([_export(tmp_path)], {"raw-a": "EST-A"}, CONFIG)
    assert all(
        r.increment.ts.utcoffset() == datetime(2025, 1, 1, tzinfo=TZ).utcoffset() for r in rows
    )
