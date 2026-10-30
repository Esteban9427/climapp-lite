"""Tests del comando que entrena, evalúa y publica pronósticos (TASK-008)."""

import json
from datetime import date
from pathlib import Path

import openpyxl
import pytest

from climapp.config import Settings
from climapp.data.daily import write_daily_csv
from climapp.forecast.cli import train_and_publish
from tests.conftest import rewrite_env
from tests.forecast.synthetic import synthetic_rows


def _chirps(path: Path) -> Path:
    book = openpyxl.Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["FECHA", 598])
    sheet.append(["2024.12.31", 3.0])
    book.save(path)
    return path


def _settings(env_file: Path, **changes: str) -> Settings:
    data_dir = env_file.parent / "data"
    write_daily_csv(synthetic_rows(), data_dir / "derived" / "daily.csv")
    _chirps(data_dir / "chirps.xlsx")
    rewrite_env(
        env_file,
        DAILY_STATIONS_FILE="derived/daily.csv",
        CHIRPS_FILES='["chirps.xlsx"]',
        RF_N_ESTIMATORS="5",
        **changes,
    )
    return Settings(_env_file=env_file)


def test_writes_evaluation_and_forecasts(env_file: Path) -> None:
    settings = _settings(env_file)
    evaluation_path, forecasts_path = train_and_publish(settings)
    report = json.loads(evaluation_path.read_text(encoding="utf-8"))
    assert [m["name"] for m in report["scenarios"]["con_est_b"]] == [
        "rf",
        "rf",
        "rf",
        "rf",
        "climatology",
        "persistence",
    ]
    assert report["data_plan"] == "plan_b_earthdata"
    forecasts = json.loads(forecasts_path.read_text(encoding="utf-8"))
    latest = [f for f in forecasts if f["variant"] == "operativa"][-1]
    assert latest["target_date"] == "2026-11-01"
    assert 0.0 <= latest["prob_ge_threshold"] <= 1.0
    assert latest["model_version"]
    assert "EST-A" in latest["inputs_available"] or "EST-B" in latest["inputs_available"]


def test_forecasts_cover_the_test_period_for_replay(env_file: Path) -> None:
    _, forecasts_path = train_and_publish(_settings(env_file))
    issued = {date.fromisoformat(f["issue_date"]) for f in json.loads(forecasts_path.read_text())}
    assert date(2024, 12, 31) in issued  # E1: emisión del día anterior al evento
    assert min(issued) == date(2022, 12, 31)


def test_chirps_counts_as_input_when_available(env_file: Path) -> None:
    _, forecasts_path = train_and_publish(_settings(env_file))
    by_key = {(f["variant"], f["issue_date"]): f for f in json.loads(forecasts_path.read_text())}
    assert "CHIRPS" in by_key["historica", "2024-12-31"]["inputs_available"]
    assert "CHIRPS" not in by_key["historica", "2025-01-01"]["inputs_available"]
    assert "CHIRPS" not in by_key["operativa", "2024-12-31"]["inputs_available"]


def test_both_variants_are_published_for_every_issue_date(env_file: Path) -> None:
    _, forecasts_path = train_and_publish(_settings(env_file))
    forecasts = json.loads(forecasts_path.read_text())
    operational = {f["issue_date"] for f in forecasts if f["variant"] == "operativa"}
    historical = {f["issue_date"] for f in forecasts if f["variant"] == "historica"}
    assert operational == historical


def test_accum_3d_level_uses_the_configured_threshold(env_file: Path) -> None:
    _, forecasts_path = train_and_publish(_settings(env_file, ACCUM3_THRESHOLD_MM="1"))
    levels = {f["accum_3d_level"] for f in json.loads(forecasts_path.read_text())}
    assert "elevado" in levels


@pytest.mark.parametrize("plan", ["principal", "plan_b_datos"])
def test_plans_not_implemented_yet_are_rejected(env_file: Path, plan: str) -> None:
    with pytest.raises(ValueError, match="TASK-0"):
        train_and_publish(_settings(env_file, DATA_PLAN=plan))

