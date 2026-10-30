"""Evaluación del RF frente a climatología y persistencia en el periodo apartado.

Los tres modelos se evalúan sobre los mismos días: objetivo observado y observación del
día de emisión disponible (la persistencia la necesita). El umbral de decisión de cada
modelo se fija en validación (ADR-001 §10); los imputados no entran (ADR-004 §3).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel

from climapp.config import DataPlan, TargetRule
from climapp.forecast.baselines import climatology_probs, fit_persistence
from climapp.forecast.dataset import Periods, Sample, split_samples
from climapp.forecast.metrics import EvalRecord, ModelMetrics, best_threshold, evaluate
from climapp.forecast.model import CalibratedForest, RFParams, fit_forest

Outcome = Literal["acierto", "falsa_alarma", "fallo", "correcto_negativo"]
OUTCOMES: dict[tuple[bool, bool], Outcome] = {
    (True, True): "acierto",
    (True, False): "falsa_alarma",
    (False, True): "fallo",
    (False, False): "correcto_negativo",
}


@dataclass(frozen=True, slots=True)
class EvalConfig:
    """Parámetros de la evaluación (todos salen de `Settings`)."""

    periods: Periods
    rf: RFParams
    window_days: int
    n_bins: int
    threshold_mm: float
    rule: TargetRule
    data_plan: DataPlan


class TestPeriod(BaseModel):
    """Periodo apartado de prueba."""

    __test__ = False  # no es una clase de tests de pytest
    start: date
    end: date


class Scenarios(BaseModel):
    """Métricas con y sin EST-B; `sin_est_b` vacío hasta TASK-029 (Should)."""

    con_est_b: list[ModelMetrics]
    sin_est_b: list[ModelMetrics]


class DailyOutcome(BaseModel):
    """Resultado del RF en un día de prueba (para el mapa)."""

    date: date
    prob: float
    observed: bool | None
    outcome: Outcome


class EvaluationReport(BaseModel):
    """`EvaluationReport` de `docs/openapi.yaml`."""

    test_period: TestPeriod
    target_rule: TargetRule
    threshold_mm: float
    data_plan: DataPlan
    scenarios: Scenarios
    sensitivity: None = None
    imerg_final_vs_early: None = None
    daily: list[DailyOutcome]
    excluded_imputed_days: int


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """Informe y modelo ajustado (el modelo se reutiliza para publicar pronósticos)."""

    report: EvaluationReport
    model: CalibratedForest


def _comparable(samples: Sequence[Sample]) -> list[Sample]:
    """Días evaluables por los tres modelos."""
    return [s for s in samples if s.observed is not None and s.today_observed is not None]


def _records(samples: Sequence[Sample], probs: Sequence[float]) -> list[EvalRecord]:
    """Registros de evaluación a partir de muestras y probabilidades."""
    return [
        EvalRecord(s.target_date, p, s.observed, s.imputed)
        for s, p in zip(samples, probs, strict=True)
    ]


def _threshold(samples: Sequence[Sample], probs: Sequence[float]) -> float:
    """Umbral que maximiza el CSI en validación (sin imputados)."""
    kept = [(bool(s.observed), p) for s, p in zip(samples, probs, strict=True) if not s.imputed]
    return best_threshold([o for o, _ in kept], [p for _, p in kept])


def _model_metrics(
    name: str,
    valid: tuple[list[Sample], list[float]],
    test: tuple[list[Sample], list[float]],
    n_bins: int,
) -> ModelMetrics:
    """Fija el umbral en validación y evalúa en prueba."""
    threshold = _threshold(*valid)
    return evaluate(_records(*test), name, threshold, n_bins)


def _baselines(
    train: Sequence[Sample], valid: list[Sample], test: list[Sample], config: EvalConfig
) -> list[ModelMetrics]:
    """Métricas de climatología y persistencia ajustadas solo con entrenamiento."""
    observed = {s.target_date: s.observed for s in train}
    clim = [
        climatology_probs(observed, [s.target_date for s in part], config.window_days)
        for part in (valid, test)
    ]
    persistence = fit_persistence(observed)
    pers_test = [persistence.prob(bool(s.today_observed)) for s in test]
    pers_threshold = persistence.prob(True)  # alerta solo si hoy hubo evento
    return [
        _model_metrics("climatology", (valid, clim[0]), (test, clim[1]), config.n_bins),
        evaluate(_records(test, pers_test), "persistence", pers_threshold, config.n_bins),
    ]


def _daily(test: Sequence[Sample], probs: Sequence[float], threshold: float) -> list[DailyOutcome]:
    """Resultado del RF por día de prueba no imputado."""
    return [
        DailyOutcome(
            date=s.target_date,
            prob=p,
            observed=s.observed,
            outcome=OUTCOMES[(p >= threshold, bool(s.observed))],
        )
        for s, p in zip(test, probs, strict=True)
        if not s.imputed
    ]


def run_evaluation(samples: Sequence[Sample], config: EvalConfig) -> EvaluationResult:
    """Ajusta el RF, evalúa las tres alternativas y arma el informe."""
    parts = split_samples(samples, config.periods)
    model = fit_forest(parts["train"], parts["valid"], config.rf)
    valid, test = _comparable(parts["valid"]), _comparable(parts["test"])
    rf_valid, rf_test = model.predict(valid), model.predict(test)
    rf = _model_metrics("rf", (valid, rf_valid), (test, rf_test), config.n_bins)
    report = EvaluationReport(
        test_period=TestPeriod(
            start=min(s.target_date for s in parts["test"]), end=config.periods.test_end
        ),
        target_rule=config.rule,
        threshold_mm=config.threshold_mm,
        data_plan=config.data_plan,
        scenarios=Scenarios(
            con_est_b=[rf, *_baselines(parts["train"], valid, test, config)], sin_est_b=[]
        ),
        daily=_daily(test, rf_test, rf.threshold),
        excluded_imputed_days=rf.excluded_imputed_days,
    )
    return EvaluationResult(report, model)
