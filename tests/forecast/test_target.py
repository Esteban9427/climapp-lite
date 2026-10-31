"""Tests del objetivo de cuenca (TASK-006, ADR-001 §2). Datos sintéticos."""

from datetime import date

import pytest

from climapp.data.models import DailyPrecip
from climapp.forecast.target import basin_days, observed_event

D = date(2024, 12, 31)


def _row(series: str, mm: float | None, *, day: date = D, imputed: bool = False) -> DailyPrecip:
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


def test_basin_mean_with_four_stations() -> None:
    day = basin_days(
        [_row("EST-A", 10.0), _row("EST-B", 20.0), _row("EST-C", 30.0), _row("EST-D", 40.0)]
    )[D]
    assert day.n_stations == 4
    assert day.mean_mm == pytest.approx(25.0)
    assert day.max_mm == pytest.approx(40.0)
    assert day.std_mm == pytest.approx(11.1803, abs=1e-4)  # desviación poblacional


def test_basin_mean_with_two_stations_ignores_invalid_days() -> None:
    day = basin_days([_row("EST-A", 18.0), _row("EST-B", None), _row("EST-C", 24.0)])[D]
    assert (day.n_stations, day.mean_mm) == (2, pytest.approx(21.0))


def test_basin_with_one_station_has_zero_spread() -> None:
    day = basin_days([_row("EST-A", 12.0)])[D]
    assert (day.n_stations, day.mean_mm, day.std_mm) == (1, 12.0, 0.0)


def test_day_without_valid_stations_has_no_value() -> None:
    day = basin_days([_row("EST-A", None), _row("EST-B", None)])[D]
    assert (day.n_stations, day.mean_mm, day.max_mm, day.std_mm) == (0, None, None, None)
    assert observed_event(day, "basin_mean", 20.0) is None


def test_imputed_values_never_enter_the_target() -> None:
    day = basin_days([_row("EST-A", 10.0), _row("EST-B", 90.0, imputed=True)])[D]
    assert (day.n_stations, day.mean_mm) == (1, 10.0)


def test_non_station_series_are_ignored() -> None:
    day = basin_days([_row("EST-A", 10.0), _row("CHIRPS_598", 50.0)])[D]
    assert day.n_stations == 1


@pytest.mark.parametrize(("mm", "expected"), [(19.99, False), (20.0, True), (35.0, True)])
def test_event_is_basin_mean_at_or_above_threshold(mm: float, expected: bool) -> None:
    day = basin_days([_row("EST-A", mm)])[D]
    assert observed_event(day, "basin_mean", 20.0) is expected


def test_threshold_comes_from_the_caller() -> None:
    day = basin_days([_row("EST-A", 12.0)])[D]
    assert observed_event(day, "basin_mean", 10.0) is True


def test_alternative_rules_are_not_available_yet() -> None:
    day = basin_days([_row("EST-A", 12.0)])[D]
    with pytest.raises(ValueError, match="TASK-032"):
        observed_event(day, "any_station", 20.0)


def test_days_are_grouped_by_date() -> None:
    other = date(2025, 1, 1)
    days = basin_days([_row("EST-A", 1.0), _row("EST-A", 3.0, day=other)])
    assert sorted(days) == [D, other]
