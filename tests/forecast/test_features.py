"""Tests de las variables del modelo (TASK-008, ADR-001 §3). Datos sintéticos."""

import math
from datetime import date, timedelta

import pytest

from climapp.data.chirps_reader import ChirpsValue
from climapp.data.models import DailyPrecip
from climapp.forecast.features import (
    FEATURE_NAMES,
    chirps_daily_mean,
    feature_row,
    variant_columns,
)
from climapp.forecast.target import basin_days
from tests.forecast.synthetic import _row, synthetic_rows

T = date(2024, 12, 31)


def _value(row_names: tuple[str, ...], values: tuple[float, ...], name: str) -> float:
    return values[row_names.index(name)]


def _rows() -> list[DailyPrecip]:
    return [
        _row(T - timedelta(days=2), "EST-A", 2.0),
        _row(T - timedelta(days=1), "EST-A", 4.0),
        _row(T - timedelta(days=1), "EST-B", 8.0),
        _row(T, "EST-A", 10.0),
        _row(T, "EST-B", None),
        _row(T, "EST-C", 30.0),
    ]


def test_aggregates_use_the_stations_available_each_day() -> None:
    row = feature_row(T, basin_days(_rows()), {})
    get = lambda name: _value(FEATURE_NAMES, row.values, name)  # noqa: E731
    assert get("mean_t0") == pytest.approx(20.0)  # EST-B sin dato no entra
    assert get("max_t0") == pytest.approx(30.0)
    assert get("std_t0") == pytest.approx(10.0)
    assert get("n_stations_t0") == 2
    assert get("mean_t1") == pytest.approx(6.0)
    assert get("mean_t2") == pytest.approx(2.0)
    assert get("accum3_mean") == pytest.approx(28.0)


def test_missing_days_become_nan() -> None:
    row = feature_row(T + timedelta(days=5), basin_days(_rows()), {})
    get = lambda name: _value(FEATURE_NAMES, row.values, name)  # noqa: E731
    assert math.isnan(get("mean_t0"))
    assert get("n_stations_t0") == 0
    assert math.isnan(get("accum3_mean"))
    assert math.isnan(get("chirps_t0"))


def test_chirps_is_the_mean_of_the_cells_and_enters_with_lag() -> None:
    chirps = chirps_daily_mean(
        [
            ChirpsValue(T, 598, 3.0),
            ChirpsValue(T, 599, 5.0),
            ChirpsValue(T - timedelta(1), 598, 1.0),
        ]
    )
    row = feature_row(T, basin_days(_rows()), chirps)
    assert _value(FEATURE_NAMES, row.values, "chirps_t0") == pytest.approx(4.0)
    assert _value(FEATURE_NAMES, row.values, "chirps_t1") == pytest.approx(1.0)


def test_chirps_cells_without_value_are_ignored() -> None:
    assert chirps_daily_mean([ChirpsValue(T, 598, None), ChirpsValue(T, 599, 2.0)]) == {T: 2.0}


def test_seasonality_is_of_the_target_day() -> None:
    row = feature_row(T, basin_days(_rows()), {})  # mañana = 1 de enero
    assert _value(FEATURE_NAMES, row.values, "doy_sin") == pytest.approx(
        math.sin(2 * math.pi / 365.25)
    )
    assert row.target_date == date(2025, 1, 1)


def test_features_never_use_data_after_the_issue_date() -> None:
    rows = synthetic_rows()
    issue = date(2022, 12, 31)
    truncated = [r for r in rows if r.date <= issue]
    assert len(truncated) < len(rows)
    full = feature_row(issue, basin_days(rows), {})
    past_only = feature_row(issue, basin_days(truncated), {})
    assert full.values == pytest.approx(past_only.values, nan_ok=True)


def test_operational_variant_uses_only_next_day_data() -> None:
    names = [FEATURE_NAMES[i] for i in variant_columns("operativa")]
    assert names
    assert not [n for n in names if n.startswith("chirps")]
    assert variant_columns("historica") == tuple(range(len(FEATURE_NAMES)))
