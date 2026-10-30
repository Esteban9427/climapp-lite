"""Tests de las métricas de verificación (TASK-007, ADR-001 §10). Casos calculados a mano."""

from datetime import date, timedelta

import pytest

from climapp.forecast.metrics import (
    EvalRecord,
    auc,
    best_threshold,
    brier,
    contingency,
    evaluate,
    reliability,
)

OBS = [True, True, True, False, False, False, False, False]
PROBS = [0.9, 0.6, 0.2, 0.7, 0.3, 0.1, 0.1, 0.05]


def test_contingency_counts_at_threshold() -> None:
    # alerta si p >= 0.5: aciertos 2, fallos 1, falsas alarmas 1, correctos negativos 4
    assert contingency(OBS, PROBS, 0.5) == (2, 1, 1, 4)


def test_scores_from_contingency() -> None:
    metrics = evaluate(_records(OBS, PROBS), "rf", threshold=0.5, n_bins=10)
    assert metrics.pod == pytest.approx(2 / 3)
    assert metrics.far == pytest.approx(1 / 3)
    assert metrics.csi == pytest.approx(2 / 4)


def test_brier_score() -> None:
    assert brier([True, False], [0.8, 0.4]) == pytest.approx(((0.2**2) + (0.4**2)) / 2)


def test_auc_counts_ties_as_half() -> None:
    # 3 eventos x 5 no eventos = 15 pares; ordenados bien: 0.9>todos(5), 0.6>4, 0.2>3 = 12
    assert auc(OBS, PROBS) == pytest.approx(12 / 15)
    assert auc([True, False], [0.5, 0.5]) == pytest.approx(0.5)


def test_auc_needs_both_classes() -> None:
    with pytest.raises(ValueError, match="ambas clases"):
        auc([True, True], [0.2, 0.3])


def test_far_without_alerts_is_zero_and_pod_without_events_fails() -> None:
    assert evaluate(_records([True, False], [0.1, 0.1]), "rf", 0.5, 10).far == 0.0
    with pytest.raises(ValueError, match="eventos"):
        evaluate(_records([False, False], [0.1, 0.9]), "rf", 0.5, 10)


def test_reliability_bins_mean_forecast_and_observed_frequency() -> None:
    bins = reliability([True, False, True, False], [0.05, 0.08, 0.91, 0.95], n_bins=10)
    assert [(b.bin, b.n) for b in bins] == [("0.0-0.1", 2), ("0.9-1.0", 2)]
    assert bins[0].forecast == pytest.approx(0.065)
    assert bins[0].observed == pytest.approx(0.5)
    assert bins[1].observed == pytest.approx(0.5)


def test_probability_one_falls_in_the_last_bin() -> None:
    assert reliability([True], [1.0], n_bins=10)[0].bin == "0.9-1.0"


def test_best_threshold_maximizes_csi() -> None:
    # p >= 0.6: H2 M1 F1 → CSI 0,5; p >= 0.2: H3 M0 F2 → CSI 0,6 (el máximo)
    assert best_threshold(OBS, PROBS) == pytest.approx(0.2)


def test_imputed_and_unobserved_days_never_enter_the_evaluation() -> None:
    records = [
        *_records(OBS, PROBS),
        EvalRecord(date(2025, 1, 1), 0.99, False, imputed=True),
        EvalRecord(date(2025, 1, 2), 0.99, None, imputed=False),
    ]
    metrics = evaluate(records, "rf", threshold=0.5, n_bins=10)
    assert metrics.far == pytest.approx(1 / 3)  # sin la falsa alarma imputada
    assert metrics.n_days == len(OBS)
    assert metrics.excluded_imputed_days == 1


def _records(obs: list[bool], probs: list[float]) -> list[EvalRecord]:
    start = date(2024, 1, 1)
    return [
        EvalRecord(start + timedelta(days=i), p, o, imputed=False)
        for i, (o, p) in enumerate(zip(obs, probs, strict=True))
    ]
