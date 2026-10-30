"""Tests de la tabla diaria de estaciones (TASK-004, ADR-004). Datos sintéticos."""

import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from climapp.data.cleaning import CleaningParams
from climapp.data.daily import (
    DailyConfig,
    MergedReadings,
    SourcedReadings,
    build_station_daily,
    daily_for_station,
    load_station_map,
    local_day,
    merge_sources,
    write_daily_csv,
)
from climapp.data.models import DailyPrecip, Reading

TZ = ZoneInfo("America/Bogota")
STEP = timedelta(minutes=10)
PARAMS = CleaningParams(
    max_step_mm=40.0,
    suspect_step_mm=30.0,
    suspect_quiet=timedelta(hours=1),
    suspect_quiet_max_mm=0,
    max_gap=timedelta(minutes=20),
)
CONFIG = DailyConfig(sensors=("P",), tz=TZ, cleaning=PARAMS, min_readings=100)
DAY = date(2024, 12, 31)
MIDNIGHT = datetime(2024, 12, 31, 0, 0, tzinfo=TZ)


def _day_readings(n: int, start: float = 0.0, rain_per_step: float = 0.1) -> list[Reading]:
    """`n` lecturas de 10 min que cierran pasos del día `DAY` (00:10 en adelante)."""
    return [
        Reading("raw-a", "P", MIDNIGHT + (i + 1) * STEP, start + (i + 1) * rain_per_step)
        for i in range(n)
    ]


def _with_opening(readings: list[Reading], value: float = 0.0) -> list[Reading]:
    """Agrega la lectura de las 00:00, que abre el primer paso del día."""
    return [Reading("raw-a", "P", MIDNIGHT, value), *readings]


def _src(readings: list[Reading], digest: str = "h1") -> SourcedReadings:
    return SourcedReadings(source_hash=digest, readings=readings)


def _station(merged: MergedReadings) -> list[tuple[Reading, str]]:
    return merged.readings_by_station["raw-a"]


def _one_day(readings: list[Reading], min_readings: int = 100) -> DailyPrecip:
    rows = daily_for_station(
        "EST-A", _station(merge_sources([_src(readings)])), PARAMS, min_readings
    )
    return next(r for r in rows if r.date == DAY)


# --- día local ---------------------------------------------------------------


def test_reading_at_midnight_closes_the_previous_local_day() -> None:
    assert local_day(datetime(2025, 1, 1, 0, 0, tzinfo=TZ)) == DAY
    assert local_day(datetime(2025, 1, 1, 0, 10, tzinfo=TZ)) == date(2025, 1, 1)
    assert local_day(datetime(2024, 12, 31, 23, 50, tzinfo=TZ)) == DAY


def test_utc_timestamps_are_converted_to_local_day() -> None:
    late_utc = datetime(2025, 1, 1, 3, 0, tzinfo=ZoneInfo("UTC"))  # 22:00 local del 31
    assert local_day(late_utc, TZ) == DAY


# --- borde de lecturas válidas ----------------------------------------------


def test_day_with_100_readings_is_valid_and_sums_increments() -> None:
    row = _one_day(_with_opening(_day_readings(100)))
    assert row.valid is True
    assert row.n_readings == 100
    assert row.precip_mm == pytest.approx(10.0)
    assert row.imputed is False
    assert row.series_id == "EST-A"


def test_day_with_99_readings_is_invalid_and_has_no_precip() -> None:
    row = _one_day(_with_opening(_day_readings(99)))
    assert row.valid is False
    assert row.n_readings == 99
    assert row.precip_mm is None


def test_min_readings_is_configurable() -> None:
    assert _one_day(_with_opening(_day_readings(99)), min_readings=99).valid is True


def test_empty_values_do_not_count_as_readings() -> None:
    readings = _with_opening(_day_readings(100))
    readings[50] = Reading("raw-a", "P", readings[50].ts, None)
    assert _one_day(readings).n_readings == 99


# --- cambio de día local -------------------------------------------------------


def test_rain_is_assigned_to_the_local_day_of_the_closing_reading() -> None:
    readings = [
        Reading("raw-a", "P", datetime(2024, 12, 31, 23, 50, tzinfo=TZ), 10.0),
        Reading("raw-a", "P", datetime(2025, 1, 1, 0, 0, tzinfo=TZ), 11.0),  # 31-dic
        Reading("raw-a", "P", datetime(2025, 1, 1, 0, 10, tzinfo=TZ), 13.0),  # 1-ene
    ]
    rows = daily_for_station(
        "EST-A", _station(merge_sources([_src(readings)])), PARAMS, min_readings=1
    )
    by_day = {r.date: r for r in rows}
    assert by_day[DAY].precip_mm == pytest.approx(1.0)
    assert by_day[date(2025, 1, 1)].precip_mm == pytest.approx(2.0)


def test_days_without_readings_inside_the_period_are_emitted_invalid() -> None:
    readings = [
        Reading("raw-a", "P", datetime(2024, 12, 30, 12, 0, tzinfo=TZ), 1.0),
        Reading("raw-a", "P", datetime(2025, 1, 1, 12, 0, tzinfo=TZ), 1.0),
    ]
    rows = daily_for_station(
        "EST-A", _station(merge_sources([_src(readings)])), PARAMS, min_readings=1
    )
    gap = next(r for r in rows if r.date == DAY)
    assert (gap.n_readings, gap.valid, gap.precip_mm, gap.source_hash) == (0, False, None, "")


def test_suspect_jumps_are_kept_in_the_total_and_counted() -> None:
    readings = _with_opening(_day_readings(120, rain_per_step=0.0))
    jump_at = 60
    readings = [
        Reading(r.station, r.sensor, r.ts, (r.value or 0.0) + (38.6 if i > jump_at else 0.0))
        for i, r in enumerate(readings)
    ]
    row = _one_day(readings)
    assert row.precip_mm == pytest.approx(38.6)
    assert row.n_suspect == 1


# --- unión de exportaciones -------------------------------------------------


def test_identical_exports_are_merged_without_duplicating() -> None:
    readings = _with_opening(_day_readings(100))
    merged = merge_sources([_src(readings, "h1"), _src(list(readings), "h2")])
    rows = daily_for_station("EST-A", _station(merged), PARAMS, min_readings=100)
    row = next(r for r in rows if r.date == DAY)
    assert row.n_readings == 100
    assert row.precip_mm == pytest.approx(10.0)
    assert row.source_hash == "h1"


def test_exports_that_complement_each_other_are_joined() -> None:
    readings = _with_opening(_day_readings(100))
    merged = merge_sources([_src(readings[:60], "h1"), _src(readings[40:], "h2")])
    row = next(
        r for r in daily_for_station("EST-A", _station(merged), PARAMS, 100) if r.date == DAY
    )
    assert row.n_readings == 100
    assert row.source_hash == "h1,h2"


def test_repeated_timestamp_with_different_value_keeps_the_first_source() -> None:
    ts = MIDNIGHT + STEP
    merged = merge_sources(
        [
            _src([Reading("raw-a", "P", ts, 1.0)], "h1"),
            _src([Reading("raw-a", "PRECIP", ts, 9.0)], "h2"),
        ]
    )
    assert [(r.value, h) for r, h in merged.readings_by_station["raw-a"]] == [(1.0, "h1")]
    assert merged.conflicts == 1


# --- mapa de estaciones, archivo y comando ---------------------------------------


def test_station_map_accepts_only_public_ids(tmp_path: Path) -> None:
    path = tmp_path / "map.json"
    path.write_text(json.dumps({"raw-a": "EST-A", "raw-b": "EST-B"}), encoding="utf-8")
    assert load_station_map(path) == {"raw-a": "EST-A", "raw-b": "EST-B"}
    path.write_text(json.dumps({"raw-a": "Estación real"}), encoding="utf-8")
    with pytest.raises(ValueError, match="EST-"):
        load_station_map(path)


def _write_export(path: Path, readings: list[Reading]) -> Path:
    lines = ["STATION_ID,SENSORNAME,FECHAYHRA,ED_VALUE"]
    lines += [
        f"{r.station},{r.sensor},{r.ts:%d/%m/%Y %H:%M},{str(r.value).replace('.', ',')}"
        for r in readings
    ]
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return path


def test_build_station_daily_maps_ids_and_hashes_sources(tmp_path: Path) -> None:
    export = _write_export(tmp_path / "e.csv", _with_opening(_day_readings(100)))
    rows = build_station_daily([export], {"raw-a": "EST-A"}, CONFIG)
    row = next(r for r in rows if r.date == DAY)
    assert row.series_id == "EST-A"
    assert len(row.source_hash) == 64  # SHA-256 del archivo crudo


def test_unmapped_station_is_rejected(tmp_path: Path) -> None:
    export = _write_export(tmp_path / "e.csv", _with_opening(_day_readings(3)))
    with pytest.raises(ValueError, match="sin correspondencia"):
        build_station_daily([export], {"otra": "EST-B"}, CONFIG)


def test_unknown_export_format_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "e.parquet"
    path.write_bytes(b"")
    with pytest.raises(ValueError, match="formato"):
        build_station_daily([path], {}, CONFIG)


def test_write_daily_csv_round_trips_the_rows(tmp_path: Path) -> None:
    row = _one_day(_with_opening(_day_readings(100)))
    out = write_daily_csv([row], tmp_path / "derived" / "daily.csv")
    (record,) = csv.DictReader(out.open(encoding="utf-8"))
    assert record["date"] == "2024-12-31"
    assert record["series_id"] == "EST-A"
    assert float(record["precip_mm"]) == pytest.approx(10.0)
    assert record["valid"] == "true"
    assert record["imputed"] == "false"


def test_multi_day_gap_resuming_at_0010_does_not_add_accumulated_rain() -> None:
    before_gap = Reading("raw-a", "P", datetime(2024, 12, 27, 12, 0, tzinfo=TZ), 100.0)
    resumed = [
        Reading("raw-a", "P", MIDNIGHT + (i + 1) * STEP, 125.0 + 0.1 * i) for i in range(110)
    ]
    rows = daily_for_station("EST-A", [(r, "h1") for r in [before_gap, *resumed]], PARAMS, 100)
    row = next(r for r in rows if r.date == DAY)
    assert row.precip_mm == pytest.approx(10.9)  # sin los 25 mm acumulados durante el hueco
    assert row.n_gap == 1
    assert row.valid is True
