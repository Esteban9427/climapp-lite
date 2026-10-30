"""Tests de las líneas base climatología y persistencia (TASK-007, ADR-001 §8)."""

from datetime import date, timedelta

import pytest

from climapp.forecast.baselines import climatology_probs, fit_persistence


def test_climatology_is_event_frequency_within_the_day_of_year_window() -> None:
    train = {
        date(2020, 1, 10): True,
        date(2020, 1, 20): False,  # a 10 días: entra
        date(2020, 2, 20): True,  # a 41 días: no entra
        date(2021, 1, 15): True,
        date(2021, 1, 1): False,
    }
    (prob,) = climatology_probs(train, [date(2023, 1, 10)], window_days=15)
    assert prob == pytest.approx(2 / 4)


def test_climatology_window_wraps_around_new_year() -> None:
    train = {date(2020, 12, 25): True, date(2021, 1, 5): False, date(2021, 6, 1): True}
    (prob,) = climatology_probs(train, [date(2023, 1, 1)], window_days=10)
    assert prob == pytest.approx(0.5)


def test_climatology_ignores_days_without_observation() -> None:
    train = {date(2020, 1, 10): True, date(2020, 1, 11): None, date(2020, 1, 12): False}
    assert climatology_probs(train, [date(2023, 1, 11)], window_days=15) == [0.5]


def test_climatology_without_training_days_in_window_fails() -> None:
    with pytest.raises(ValueError, match="ventana"):
        climatology_probs({date(2020, 6, 1): True}, [date(2023, 1, 1)], window_days=15)


def test_persistence_binary_and_conditional_probability() -> None:
    days = [date(2020, 1, 1) + timedelta(days=i) for i in range(6)]
    observed = dict(zip(days, [True, True, False, False, True, False], strict=True))
    model = fit_persistence(observed)
    # pares (hoy, mañana): TT, TF, FF, FT, TF → P(T|T)=1/3, P(T|F)=1/2
    assert model.prob_after_event == pytest.approx(1 / 3)
    assert model.prob_after_no_event == pytest.approx(1 / 2)
    assert model.binary(True) == 1.0
    assert model.binary(False) == 0.0
    assert model.prob(True) == pytest.approx(1 / 3)


def test_persistence_skips_pairs_with_missing_days() -> None:
    observed = {date(2020, 1, 1): True, date(2020, 1, 2): None, date(2020, 1, 3): True}
    with pytest.raises(ValueError, match="pares"):
        fit_persistence(observed)
