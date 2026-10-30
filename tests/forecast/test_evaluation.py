"""Tests del informe de evaluación RF frente a líneas base (TASK-008, ADR-001 §8-§10)."""

from datetime import date
from functools import cache

import pytest

from climapp.forecast.dataset import build_samples
from climapp.forecast.evaluation import EvalConfig, EvaluationReport, run_evaluation
from climapp.forecast.target import basin_days
from tests.forecast.synthetic import synthetic_rows
from tests.forecast.test_model import PARAMS, PERIODS

CONFIG = EvalConfig(
    periods=PERIODS,
    rf=PARAMS,
    window_days=15,
    n_bins=10,
    threshold_mm=20.0,
    rule="basin_mean",
    data_plan="plan_b_earthdata",
)


@cache
def _report() -> EvaluationReport:
    samples = build_samples(basin_days(synthetic_rows()), {}, threshold_mm=20.0, rule="basin_mean")
    return run_evaluation(samples, CONFIG).report


def test_report_compares_both_rf_variants_with_both_baselines() -> None:
    report = _report()
    rows = [(m.name, m.variant, m.calibrated) for m in report.scenarios.con_est_b]
    assert rows == [
        ("rf", "operativa", True),
        ("rf", "operativa", False),
        ("rf", "historica", True),
        ("rf", "historica", False),
        ("climatology", None, None),
        ("persistence", None, None),
    ]
    assert report.test_period.start == date(2023, 1, 1)
    assert report.scenarios.sin_est_b == []  # TASK-029 (Should)
    assert report.sensitivity is None
    assert report.imerg_final_vs_early is None


def test_historical_variant_is_labelled_not_available_live() -> None:
    by_variant = {m.variant: m for m in _report().scenarios.con_est_b if m.calibrated}
    assert by_variant["historica"].available_live is False
    assert "retraso" in (by_variant["historica"].note or "")
    assert by_variant["operativa"].available_live is True


def test_all_models_are_evaluated_on_the_same_days() -> None:
    metrics = _report().scenarios.con_est_b
    assert len({m.n_days for m in metrics}) == 1


def test_rf_beats_climatology_on_a_persistent_synthetic_series() -> None:
    metrics = _report().scenarios.con_est_b
    rf, clim = metrics[0], metrics[4]
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
    assert report.daily_variant == "operativa"


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


def test_evaluation_without_test_days_fails_with_a_clear_message() -> None:
    rows = [r for r in synthetic_rows() if r.date < date(2022, 12, 1)]
    samples = build_samples(basin_days(rows), {}, threshold_mm=20.0, rule="basin_mean")
    with pytest.raises(ValueError, match="periodo de prueba"):
        run_evaluation(samples, CONFIG)
