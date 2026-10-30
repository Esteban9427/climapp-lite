"""Tests de la partición, el random forest calibrado y la fuga temporal (TASK-008)."""

from datetime import date

import pytest

from climapp.forecast.dataset import Periods, build_samples, split_samples
from climapp.forecast.model import RFParams, fit_forest
from climapp.forecast.target import basin_days
from tests.forecast.synthetic import synthetic_rows

PERIODS = Periods(
    train_start=date(2013, 10, 1),
    train_end=date(2021, 12, 31),
    valid_end=date(2022, 12, 31),
    test_end=date(2026, 10, 31),
)
PARAMS = RFParams(n_estimators=50, min_samples_leaf=5, random_state=0)


def _split() -> dict[str, list]:  # type: ignore[type-arg]
    samples = build_samples(basin_days(synthetic_rows()), {}, threshold_mm=20.0, rule="basin_mean")
    return split_samples(samples, PERIODS)


def test_samples_are_assigned_by_target_date() -> None:
    parts = _split()
    assert max(s.target_date for s in parts["train"]) == date(2021, 12, 31)
    assert min(s.target_date for s in parts["valid"]) == date(2022, 1, 1)
    assert min(s.target_date for s in parts["test"]) == date(2023, 1, 1)
    assert max(s.target_date for s in parts["test"]) <= PERIODS.test_end


def test_target_is_tomorrows_basin_event() -> None:
    samples = build_samples(basin_days(synthetic_rows()), {}, threshold_mm=20.0, rule="basin_mean")
    by_issue = {s.issue_date: s for s in samples}
    days = basin_days(synthetic_rows())
    s = by_issue[date(2020, 5, 1)]
    tomorrow = days[date(2020, 5, 2)]
    assert tomorrow.mean_mm is not None
    assert s.observed == (tomorrow.mean_mm >= 20.0)


def test_no_test_date_is_used_to_fit_or_calibrate() -> None:
    parts = _split()
    model = fit_forest(parts["train"], parts["valid"], PARAMS)
    test_dates = {s.target_date for s in parts["test"]}
    assert model.fitted_dates
    assert model.calibrated_dates
    assert not (model.fitted_dates | model.calibrated_dates) & test_dates
    assert max(model.fitted_dates) < min(model.calibrated_dates)


def test_calibrated_probabilities_are_bounded_and_reproducible() -> None:
    parts = _split()
    probs = fit_forest(parts["train"], parts["valid"], PARAMS).predict(parts["test"])
    again = fit_forest(parts["train"], parts["valid"], PARAMS).predict(parts["test"])
    assert all(0.0 <= p <= 1.0 for p in probs)
    assert probs == again


def test_unobserved_targets_are_not_used_for_fitting() -> None:
    parts = _split()
    model = fit_forest(parts["train"], parts["valid"], PARAMS)
    unobserved = {s.target_date for s in parts["train"] if s.observed is None}
    assert unobserved
    assert not unobserved & model.fitted_dates


def test_periods_reject_overlap() -> None:
    with pytest.raises(ValueError, match="cronológico"):
        Periods(date(2020, 1, 1), date(2022, 1, 1), date(2021, 1, 1), date(2023, 1, 1))
