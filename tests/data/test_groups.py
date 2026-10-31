"""Tests de los grupos de estaciones correlacionadas (TASK-002 mínima, ADR-002 §4).

Datos sintéticos: series inventadas, sin nombres ni coordenadas reales.
"""

import json
import random
from datetime import date, timedelta
from pathlib import Path

import pytest

from climapp.config import Settings
from climapp.data.daily import write_daily_csv
from climapp.data.groups import (
    GroupingParams,
    build_groups,
    pairwise_correlations,
    station_groups,
)
from climapp.data.models import DailyPrecip
from tests.conftest import rewrite_env

START = date(2015, 1, 1)
PARAMS = GroupingParams(start=START, end=date(2016, 12, 31), min_r=0.8, min_overlap_days=30)


def _row(series: str, day: date, mm: float | None, *, imputed: bool = False) -> DailyPrecip:
    return DailyPrecip(
        date=day,
        series_id=series,
        precip_mm=mm,
        n_readings=144 if mm is not None else 10,
        valid=mm is not None,
        imputed=imputed,
        source_hash="h",
        n_suspect=0,
        suspect_mm=0.0,
        n_gap=0,
    )


def _rain(seed: int, n: int = 200) -> list[float]:
    rng = random.Random(seed)
    return [round(rng.expovariate(1 / 5), 1) for _ in range(n)]


def _series(series: str, values: list[float | None], start: date = START) -> list[DailyPrecip]:
    return [_row(series, start + timedelta(days=i), v) for i, v in enumerate(values)]


def _correlated(values: list[float], seed: int, noise: float = 0.5) -> list[float | None]:
    rng = random.Random(seed)
    return [round(v * 1.1 + rng.uniform(0, noise), 1) for v in values]


def test_correlated_pair_is_grouped_and_independent_station_stays_alone() -> None:
    a = _rain(1)
    rows = (
        _series("EST-A", list(a))
        + _series("EST-B", _correlated(a, 2))
        + _series("EST-C", list(_rain(3)))
    )
    groups = station_groups(rows, PARAMS)
    assert groups == [("EST-A", "EST-B"), ("EST-C",)]


def test_grouping_is_transitive() -> None:
    a = _rain(1)
    b = _correlated(a, 2)
    c = _correlated([v or 0.0 for v in b], 3)
    rows = _series("EST-A", list(a)) + _series("EST-B", b) + _series("EST-C", c)
    assert station_groups(rows, PARAMS) == [("EST-A", "EST-B", "EST-C")]


def test_pair_below_min_r_is_not_grouped() -> None:
    a = _rain(1)
    rows = _series("EST-A", list(a)) + _series("EST-B", _correlated(a, 2, noise=40.0))
    (pair,) = pairwise_correlations(rows, PARAMS)
    assert pair.r < PARAMS.min_r
    assert station_groups(rows, PARAMS) == [("EST-A",), ("EST-B",)]


def test_planted_duplicate_has_r_one() -> None:
    a = _rain(1)
    rows = _series("EST-A", list(a)) + _series("EST-D", list(a))
    (pair,) = pairwise_correlations(rows, PARAMS)
    assert (pair.a, pair.b, pair.n_days) == ("EST-A", "EST-D", 200)
    assert pair.r == pytest.approx(1.0)


def test_pair_with_too_few_common_days_is_not_correlated() -> None:
    a = _rain(1)
    rows = _series("EST-A", list(a)) + _series("EST-B", list(a[:20]))
    assert pairwise_correlations(rows, PARAMS) == []
    assert station_groups(rows, PARAMS) == [("EST-A",), ("EST-B",)]


def test_only_valid_non_imputed_days_inside_the_period_count() -> None:
    a = _rain(1)
    rows = _series("EST-A", list(a)) + _series("EST-B", list(a))
    late = START + timedelta(days=900)  # fuera del periodo: no cuenta
    rows += [_row("EST-A", late, 100.0), _row("EST-B", late, 0.0)]
    rows += [_row("EST-A", START + timedelta(days=300), 50.0)]
    rows += [_row("EST-B", START + timedelta(days=300), 0.0, imputed=True)]
    (pair,) = pairwise_correlations(rows, PARAMS)
    assert pair.n_days == 200
    assert pair.r == pytest.approx(1.0)


def test_constant_series_has_no_correlation() -> None:
    rows = _series("EST-A", list(_rain(1))) + _series("EST-B", [0.0] * 200)
    assert pairwise_correlations(rows, PARAMS) == []


def test_non_station_series_are_ignored() -> None:
    a = _rain(1)
    rows = _series("EST-A", list(a)) + _series("CHIRPS_598", list(a))
    assert station_groups(rows, PARAMS) == [("EST-A",)]


def test_build_groups_writes_the_artifact(env_file: Path) -> None:
    a = _rain(1)
    rows = _series("EST-A", list(a)) + _series("EST-B", _correlated(a, 2))
    data_dir = env_file.parent / "data"
    write_daily_csv(rows, data_dir / "derived" / "daily.csv")
    rewrite_env(
        env_file,
        DAILY_STATIONS_FILE="derived/daily.csv",
        TRAIN_START="2015-01-01",
        CALIBRATION_START="2015-06-01",
        VALID_END="2016-12-31",
        STATION_GROUP_MIN_OVERLAP_DAYS="30",
    )
    out = build_groups(Settings(_env_file=env_file))
    data = json.loads(out.read_text(encoding="utf-8"))
    assert out == data_dir / "derived" / "station_groups.json"
    assert data["groups"] == [["EST-A", "EST-B"]]
    assert data["min_r"] == 0.8
    assert data["period"] == {"start": "2015-01-01", "end": "2016-12-31"}
    assert data["pairs"][0]["a"] == "EST-A"
