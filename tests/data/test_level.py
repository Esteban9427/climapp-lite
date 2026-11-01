"""Tests del lector de nivel del río y su serie diaria (TASK-038, ADR-004). Datos sintéticos."""

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import openpyxl
import pytest

from climapp.config import Settings
from climapp.data.level import (
    DailyLevel,
    LevelPoint,
    build_level_daily,
    daily_level,
    drop_single_spikes,
    read_level_csv,
    read_level_xlsx,
    write_level_csv,
)
from tests.conftest import rewrite_env

TZ = ZoneInfo("America/Bogota")
HEADER = ("STATION_ID", "SENSORNAME", "FECHAYHRA", "ED_VALUE")
RAW = "raw-a"
T0 = datetime(2025, 1, 1, 0, 0, tzinfo=TZ)

Row = tuple[object, ...]


def _book(tmp_path: Path, rows: list[Row], name: str = "nivel.xlsx") -> Path:
    book = openpyxl.Workbook()
    sheet = book.active
    assert sheet is not None
    for row in [HEADER, *rows]:
        sheet.append(list(row))
    path = tmp_path / name
    book.save(path)
    return path


def _points(levels: list[float], start: datetime = T0, step_min: int = 15) -> list[LevelPoint]:
    return [LevelPoint(start + timedelta(minutes=step_min * i), m) for i, m in enumerate(levels)]


# --- lector --------------------------------------------------------------------


def test_reads_level_rows_with_text_or_date_timestamps(tmp_path: Path) -> None:
    path = _book(
        tmp_path,
        [
            (RAW, "NIVEL", "01/01/2025 00:00", 0.42),
            (RAW, "NIVEL", datetime(2025, 1, 1, 0, 15), "0,45"),
        ],
    )
    readings = read_level_xlsx(path, "NIVEL", TZ)
    assert [(r.station, r.ts, r.value) for r in readings] == [
        (RAW, T0, 0.42),
        (RAW, T0 + timedelta(minutes=15), 0.45),
    ]


def test_other_sensors_and_empty_values_are_skipped(tmp_path: Path) -> None:
    path = _book(
        tmp_path,
        [
            (RAW, "P", "01/01/2025 00:00", 821.2),
            (RAW, "NIVEL", "01/01/2025 00:15", None),
            (RAW, "NIVEL", "01/01/2025 00:30", 0.5),
        ],
    )
    assert [r.value for r in read_level_xlsx(path, "NIVEL", TZ)] == [0.5]


def test_wrong_header_is_rejected(tmp_path: Path) -> None:
    book = openpyxl.Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["FECHA", "VALOR"])
    path = tmp_path / "otro.xlsx"
    book.save(path)
    with pytest.raises(ValueError, match="encabezado"):
        read_level_xlsx(path, "NIVEL", TZ)


def test_malformed_row_reports_its_number(tmp_path: Path) -> None:
    path = _book(tmp_path, [(RAW, "NIVEL", "01/01/2025 00:00", "alto")])
    with pytest.raises(ValueError, match="fila 2"):
        read_level_xlsx(path, "NIVEL", TZ)


# --- serie diaria --------------------------------------------------------------


def test_daily_min_max_and_count() -> None:
    (row,) = daily_level("EST-A", _points([0.40, 0.55, 0.38, 0.41]), TZ)
    assert row == DailyLevel(
        series_id="EST-A",
        date=date(2025, 1, 1),
        n_readings=4,
        level_min_m=0.38,
        level_max_m=0.55,
        rise_24h_max_m=pytest.approx(0.15),
    )


def test_rise_uses_the_minimum_of_the_previous_24_hours_across_midnight() -> None:
    # 23:00 del 31-dic en 0,30 m; el 1-ene a la 01:00 llega a 0,90 m
    points = [
        LevelPoint(T0 - timedelta(hours=1), 0.30),
        LevelPoint(T0 + timedelta(hours=1), 0.90),
    ]
    rows = {r.date: r for r in daily_level("EST-A", points, TZ)}
    assert rows[date(2025, 1, 1)].rise_24h_max_m == pytest.approx(0.60)
    assert rows[date(2025, 1, 1)].level_min_m == 0.90  # el mínimo del día no mira atrás


def test_minimum_older_than_24_hours_does_not_count() -> None:
    points = [
        LevelPoint(T0, 0.20),
        LevelPoint(T0 + timedelta(hours=24, minutes=15), 0.50),
        LevelPoint(T0 + timedelta(hours=25), 0.60),
    ]
    rows = {r.date: r for r in daily_level("EST-A", points, TZ)}
    assert rows[date(2025, 1, 2)].rise_24h_max_m == pytest.approx(0.10)


def test_minimum_exactly_24_hours_old_still_counts() -> None:
    """La ventana es cerrada: la lectura de hace exactamente 24 h entra."""
    points = [LevelPoint(T0, 0.20), LevelPoint(T0 + timedelta(hours=24), 0.50)]
    rows = {r.date: r for r in daily_level("EST-A", points, TZ)}
    assert rows[date(2025, 1, 2)].rise_24h_max_m == pytest.approx(0.30)


def test_falling_level_has_zero_rise() -> None:
    (row,) = daily_level("EST-A", _points([0.9, 0.7, 0.5]), TZ)
    assert row.rise_24h_max_m == 0.0


def test_duplicate_timestamps_keep_the_first_value_and_order_does_not_matter() -> None:
    points = [LevelPoint(T0 + timedelta(minutes=15), 0.6), LevelPoint(T0, 0.4)]
    duplicated = [*points, LevelPoint(T0, 0.1)]
    assert daily_level("EST-A", duplicated, TZ) == daily_level("EST-A", points, TZ)


def test_days_without_readings_are_not_invented() -> None:
    points = [LevelPoint(T0, 0.4), LevelPoint(T0 + timedelta(days=2), 0.4)]
    assert [r.date for r in daily_level("EST-A", points, TZ)] == [
        date(2025, 1, 1),
        date(2025, 1, 3),
    ]


# --- picos de una sola lectura (NIVEL_MAX_STEP_M, SUPUESTO) ------------------------


def test_a_single_reading_jump_and_return_is_dropped() -> None:
    points = _points([0.50, 0.52, 13.0, 0.51, 0.50])
    kept = drop_single_spikes(points, max_step_m=1.0)
    assert [p.level_m for p in kept] == [0.50, 0.52, 0.51, 0.50]


def test_a_single_reading_dip_and_return_is_dropped() -> None:
    kept = drop_single_spikes(_points([0.90, 0.88, -0.30, 0.89]), max_step_m=1.0)
    assert [p.level_m for p in kept] == [0.90, 0.88, 0.89]


def test_a_real_rise_that_stays_up_is_kept() -> None:
    points = _points([0.40, 1.60, 1.70, 1.50])
    assert drop_single_spikes(points, max_step_m=1.0) == points


def test_steps_equal_to_the_limit_and_the_series_edges_are_kept() -> None:
    inside = _points([0.40, 1.40, 0.40])  # salto y regreso de exactamente 1,0 m
    assert drop_single_spikes(inside, max_step_m=1.0) == inside
    edges = _points([9.0, 0.40, 0.41, 9.0])  # sin vecino a un lado no hay "regreso"
    assert drop_single_spikes(edges, max_step_m=1.0) == edges


def test_spikes_are_found_in_time_order_after_dropping_duplicates() -> None:
    points = _points([0.50, 13.0, 0.50])
    shuffled = [points[2], points[0], points[1], LevelPoint(points[1].ts, 0.50)]
    kept = drop_single_spikes(shuffled, max_step_m=1.0)
    assert [p.level_m for p in kept] == [0.50, 0.50]


# --- csv y comando ---------------------------------------------------------------


def test_csv_round_trip(tmp_path: Path) -> None:
    rows = daily_level("EST-A", _points([0.40, 0.55]), TZ)
    path = write_level_csv(rows, tmp_path / "derived" / "nivel.csv")
    assert read_level_csv(path) == rows


def test_build_maps_the_raw_station_to_its_public_id(env_file: Path, tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    _book(data, [(RAW, "NIVEL", "01/01/2025 00:00", 0.4), (RAW, "NIVEL", "01/01/2025 00:15", 0.7)])
    (data / "map.json").write_text(f'{{"{RAW}": "EST-A"}}', encoding="utf-8")
    settings = Settings(
        _env_file=rewrite_env(
            env_file,
            LEVEL_EXPORTS='["nivel.xlsx"]',
            STATION_MAP_FILE="map.json",
            LEVEL_DAILY_FILE="derived/nivel.csv",
        )
    )
    out = build_level_daily(settings)
    (row,) = read_level_csv(out)
    assert (row.series_id, row.rise_24h_max_m) == ("EST-A", pytest.approx(0.3))
    assert RAW not in out.read_text(encoding="utf-8")


def test_unmapped_station_is_rejected(env_file: Path, tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    _book(data, [(RAW, "NIVEL", "01/01/2025 00:00", 0.4)])
    (data / "map.json").write_text("{}", encoding="utf-8")
    settings = Settings(
        _env_file=rewrite_env(env_file, LEVEL_EXPORTS='["nivel.xlsx"]', STATION_MAP_FILE="map.json")
    )
    with pytest.raises(ValueError, match="sin correspondencia"):
        build_level_daily(settings)


def test_build_drops_single_reading_spikes(env_file: Path, tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    levels = [0.40, 0.42, 9.50, 0.41]
    rows = [(RAW, "NIVEL", f"01/01/2025 00:{15 * i:02d}", m) for i, m in enumerate(levels)]
    _book(data, rows)
    (data / "map.json").write_text(f'{{"{RAW}": "EST-A"}}', encoding="utf-8")
    settings = Settings(
        _env_file=rewrite_env(
            env_file,
            LEVEL_EXPORTS='["nivel.xlsx"]',
            STATION_MAP_FILE="map.json",
            LEVEL_DAILY_FILE="derived/nivel.csv",
            NIVEL_MAX_STEP_M="1.0",
        )
    )
    (row,) = read_level_csv(build_level_daily(settings))
    assert (row.n_readings, row.level_max_m) == (3, 0.42)
    assert row.rise_24h_max_m == pytest.approx(0.02)
