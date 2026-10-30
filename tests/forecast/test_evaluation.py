"""Tests del informe de evaluación RF frente a líneas base (TASK-008, ADR-001 §8-§10)."""

from datetime import date

import pytest

from climapp.forecast.dataset import build_samples
from climapp.forecast.evaluation import EvalConfig, EvaluationReport, run_evaluation
from climapp.forecast.target import basin_days
from tests.forecast.test_model import PARAMS, PERIODS
from tests.forecast.synthetic import synthetic_rows


CONFIG = EvalConfig(
    periods=PERIODS,
    rf=PARAMS,
    window_days=15,
    n_bins=10,
    threshold_mm=20.0,
    rule="basin_mean",
    data_plan="plan_b_earthdata",
)


def _report() -> EvaluationReport:
    samples = build_samples(basin_days(synthetic_rows()), {}, threshold_mm=20.0, rule="basin_mean")
    return run_evaluation(samples, CONFIG).report


def test_report_compares_rf_with_both_baselines_on_the_test_period() -> None:
    report = _report()
    names = [m.name for m in report.scenarios.con_est_b]
    assert names == ["rf", "climatology", "persistence"]
    assert report.test_period.start == date(2023, 1, 1)
    assert report.scenarios.sin_est_b == []  # TASK-029 (Should)
    assert report.sensitivity is None
    assert report.imerg_final_vs_early is None


def test_all_models_are_evaluated_on_the_same_days() -> None:
    metrics = _report().scenarios.con_est_b
    assert len({m.n_days for m in metrics}) == 1


def test_rf_beats_climatology_on_a_persistent_synthetic_series() -> None:
    rf, clim, _ = _report().scenarios.con_est_b
    assert rf.auc > clim.auc
    assert rf.brier < clim.brier


def test_daily_outcomes_follow_the_validation_threshold() -> None:
    report = _report()
    rf = report.scenarios.con_est_b[0]
    for day in report.daily:
        alert = day.prob >= rf.threshold
        expected = {
            (True, True): "acierto",
            (True, False): "falsa_alarma",
            (False, True): "fallo",
            (False, False): "correcto_negativo",
        }[(alert, bool(day.observed))]
        assert day.outcome == expected
    assert len(report.daily) == rf.n_days


def test_daily_entries_are_only_test_days() -> None:
    assert min(d.date for d in _report().daily) >= date(2023, 1, 1)


def test_report_carries_rule_threshold_and_data_plan() -> None:
    report = _report()
    assert (report.target_rule, report.threshold_mm, report.data_plan) == (
        "basin_mean",
        20.0,
        "plan_b_earthdata",
    )
    assert report.excluded_imputed_days == 0
