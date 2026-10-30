"""Tests de la partición, el random forest calibrado y la fuga temporal (TASK-008)."""

from dataclasses import replace
from datetime import date
from functools import cache

import pytest

from climapp.forecast.dataset import Part, Periods, Sample, build_samples, split_samples
from climapp.forecast.features import FEATURE_NAMES, variant_columns
from climapp.forecast.model import RFParams, fit_forest
from climapp.forecast.target import basin_days
from tests.forecast.synthetic import synthetic_rows

PERIODS = Periods(
    train_start=date(2013, 10, 1),
    calibration_start=date(2020, 1, 1),
    valid_end=date(2022, 12, 31),
    test_end=date(2026, 10, 31),
)
ALL = variant_columns("historica")
PARAMS = RFParams(n_estimators=50, min_samples_leaf=5, random_state=0)


@cache
def _split() -> dict[Part, list[Sample]]:
    samples = build_samples(basin_days(synthetic_rows()), {}, threshold_mm=20.0, rule="basin_mean")
    return split_samples(samples, PERIODS)


def test_samples_are_assigned_by_target_date() -> None:
    parts = _split()
    assert max(s.target_date for s in parts["train"]) == date(2019, 12, 31)
    assert min(s.target_date for s in parts["valid"]) == date(2020, 1, 1)
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
    model = fit_forest(parts["train"], parts["valid"], PARAMS, ALL)
    test_dates = {s.target_date for s in parts["test"]}
    assert model.fitted_dates
    assert model.calibrated_dates
    assert not (model.fitted_dates | model.calibrated_dates) & test_dates
    assert max(model.fitted_dates) == date(2022, 12, 31)  # el bosque final usa todo lo previo


def test_each_calibration_fold_is_out_of_sample() -> None:
    parts = _split()
    model = fit_forest(parts["train"], parts["valid"], PARAMS, ALL)
    assert [min(f.predicted).year for f in model.folds] == [2020, 2021, 2022]
    for fold in model.folds:
        assert fold.train_max < min(fold.predicted)
        assert {d.year for d in fold.predicted} == {min(fold.predicted).year}
    assert model.calibrated_dates == frozenset().union(*(f.predicted for f in model.folds))


def test_operational_variant_ignores_chirps_columns() -> None:
    parts = _split()
    columns = variant_columns("operativa")
    model = fit_forest(parts["train"], parts["valid"], PARAMS, columns)
    chirps = [FEATURE_NAMES.index("chirps_t0"), FEATURE_NAMES.index("chirps_t1")]
    altered = [
        replace(s, x=tuple(99.0 if i in chirps else v for i, v in enumerate(s.x)))
        for s in parts["test"][:50]
    ]
    assert model.predict(altered) == model.predict(parts["test"][:50])


def test_uncalibrated_probabilities_are_the_forest_votes() -> None:
    parts = _split()
    model = fit_forest(parts["train"], parts["valid"], PARAMS, ALL)
    raw = model.predict(parts["test"][:20], calibrated=False)
    assert raw == [float(p) for p in model.raw(parts["test"][:20])]


def test_calibrated_probabilities_are_bounded_and_reproducible() -> None:
    parts = _split()
    probs = fit_forest(parts["train"], parts["valid"], PARAMS, ALL).predict(parts["test"])
    again = fit_forest(parts["train"], parts["valid"], PARAMS, ALL).predict(parts["test"])
    assert all(0.0 <= p <= 1.0 for p in probs)
    assert probs == again


def test_unobserved_targets_are_not_used_for_fitting() -> None:
    parts = _split()
    model = fit_forest(parts["train"], parts["valid"], PARAMS, ALL)
    unobserved = {s.target_date for s in parts["train"] if s.observed is None}
    assert unobserved
    assert not unobserved & model.fitted_dates


def test_periods_reject_overlap() -> None:
    with pytest.raises(ValueError, match="cronológico"):
        Periods(date(2020, 1, 1), date(2022, 1, 1), date(2021, 1, 1), date(2023, 1, 1))
