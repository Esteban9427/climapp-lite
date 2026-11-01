"""Contexto del pronóstico calculado por código (ADR-001 §11). Datos sintéticos.

El acumulado de 3 días se compara con la serie de entrenamiento (percentil) y la
probabilidad con la climatología del día y con el umbral de aviso de la variante.
Nada de esto cambia el modelo.
"""

from datetime import date, timedelta

import pytest

from climapp.forecast.context import (
    ForecastContext,
    build_context,
    risk_level,
)
from climapp.forecast.target import BasinDay

START, END = date(2020, 1, 1), date(2020, 1, 10)


def _basin(values: dict[date, float]) -> dict[date, BasinDay]:
    return {d: BasinDay(d, 1, mm, mm, 0.0) for d, mm in values.items()}


def _context(values: dict[date, float]) -> ForecastContext:
    return build_context(
        _basin(values), start=START, end=END, threshold_mm=20.0, rule="basin_mean", window_days=15
    )


def test_training_accumulations_are_three_day_sums_inside_the_period() -> None:
    days = {START + timedelta(days=i): float(i) for i in range(12)}  # 0, 1, …, 11 mm
    ctx = _context(days)
    # emisiones del 01-03 al 01-10 con sus dos días previos: 0+1+2 = 3 … 7+8+9 = 24
    assert ctx.accum3_train == (3.0, 6.0, 9.0, 12.0, 15.0, 18.0, 21.0, 24.0)


def test_percentile_is_the_share_of_training_days_below_the_value() -> None:
    ctx = _context({START + timedelta(days=i): float(i) for i in range(12)})
    assert ctx.accum3_percentile(13.0) == 50  # 4 de 8 días quedan por debajo
    assert ctx.accum3_percentile(100.0) == 100
    assert ctx.accum3_percentile(3.0) == 0  # igual no cuenta como "más que"
    assert ctx.accum3_percentile(None) is None


def test_days_with_a_missing_lag_do_not_enter_the_training_series() -> None:
    days = {START + timedelta(days=i): 1.0 for i in range(12) if i != 5}
    assert len(_context(days).accum3_train) == 5  # 3 emisiones pierden el 01-06


def test_climatology_is_the_event_frequency_around_the_target_day() -> None:
    days = {START + timedelta(days=i): (25.0 if i % 4 == 0 else 1.0) for i in range(10)}
    ctx = _context(days)
    assert ctx.climatology(date(2023, 1, 5)) == pytest.approx(3 / 10)


def test_climatology_without_training_days_near_the_target_is_none() -> None:
    ctx = _context({START + timedelta(days=i): 1.0 for i in range(10)})
    assert ctx.climatology(date(2023, 7, 1)) is None


@pytest.mark.parametrize(
    ("prob", "threshold", "level"),
    [
        (0.149, 0.132, "elevado"),
        (0.132, 0.132, "elevado"),
        (0.112, 0.132, "habitual"),
        (0.2, None, None),
    ],
)
def test_risk_level_compares_with_the_variant_warning_threshold(
    prob: float, threshold: float | None, level: str | None
) -> None:
    assert risk_level(prob, threshold) == level
