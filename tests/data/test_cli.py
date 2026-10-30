"""Tests del comando que regenera la tabla diaria de estaciones (TASK-004, ADR-004 §4)."""

import csv
import json
from pathlib import Path

import pytest

from climapp.config import Settings
from climapp.data.cli import build_daily, main
from tests.conftest import rewrite_env

EXPORT = """STATION_ID,SENSORNAME,FECHAYHRA,ED_VALUE
raw-a,P,31/12/2024 23:40,10
raw-a,P,31/12/2024 23:50,10,4
raw-a,P,01/01/2025 00:00,11
"""


def _prepare(env_file: Path) -> Path:
    data_dir = env_file.parent / "data"
    (data_dir / "raw").mkdir(parents=True)
    (data_dir / "raw" / "e.csv").write_text(EXPORT, encoding="ascii")
    (data_dir / "map.json").write_text(json.dumps({"raw-a": "EST-A"}), encoding="utf-8")
    return rewrite_env(
        env_file,
        STATION_EXPORTS='["raw/e.csv"]',
        STATION_MAP_FILE="map.json",
        DAILY_STATIONS_FILE="derived/daily.csv",
        MIN_READINGS="3",
    )


def test_build_daily_writes_the_table_under_data_dir(env_file: Path) -> None:
    settings = Settings(_env_file=_prepare(env_file))
    out = build_daily(settings)
    assert out == settings.data_dir / "derived" / "daily.csv"
    (row,) = csv.DictReader(out.open(encoding="utf-8"))
    assert (row["date"], row["series_id"], row["valid"]) == ("2024-12-31", "EST-A", "true")
    assert float(row["precip_mm"]) == pytest.approx(1.0)


def test_main_reads_settings_from_environment(
    env_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for line in _prepare(env_file).read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        monkeypatch.setenv(key, value)
    monkeypatch.chdir(env_file.parent.parent)  # sin .env en el directorio actual
    main()
    assert (env_file.parent / "data" / "derived" / "daily.csv").exists()
