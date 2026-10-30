"""Evaluación del RF frente a climatología y persistencia en el periodo apartado.

Todos los modelos se evalúan sobre los mismos días: objetivo observado y observación del
día de emisión disponible (la persistencia la necesita). El umbral de decisión de cada
modelo se fija con las predicciones fuera de muestra de validación (ADR-001 §10); los
imputados no entran (ADR-004 §3). El RF se reporta por variante (operativa e
histórica) y calibrado y sin calibrar (ADR-001 §1, §3 y §5, revisión del 2026-10-30).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel

from climapp.config import DataPlan, TargetRule
from climapp.forecast.baselines import climatology_probs, fit_persistence
from climapp.forecast.dataset import Periods, Sample, split_samples
from climapp.forecast.features import VARIANTS, Variant, variant_columns
from climapp.forecast.metrics import EvalRecord, ModelMetrics, best_threshold, evaluate
from climapp.forecast.model import CalibratedForest, RFParams, fit_forest

Outcome = Literal["acierto", "falsa_alarma", "fallo", "correcto_negativo"]
OUTCOMES: dict[tuple[bool, bool], Outcome] = {
    (True, True): "acierto",
    (True, False): "falsa_alarma",
    (False, True): "fallo",
    (False, False): "correcto_negativo",
}
LIVE_NOTES: dict[Variant, str | None] = {
    "operativa": None,
    "historica": "requiere datos con semanas de retraso (CHIRPS); no disponible en vivo",
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
    daily_variant: Variant
    excluded_imputed_days: int


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """Informe y modelo ajustado (el modelo se reutiliza para publicar pronósticos)."""

    report: EvaluationReport
    models: dict[Variant, CalibratedForest]


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
    history: Sequence[Sample], valid: list[Sample], test: list[Sample], config: EvalConfig
) -> list[ModelMetrics]:
    """Métricas de climatología y persistencia ajustadas con `history`.

    `history` es todo lo previo a la prueba (≤ `VALID_END`), igual que el bosque final
    (ADR-001 §1). El umbral de la climatología se fija con la validación, que está dentro
    de ese ajuste: limitación conocida (ADR-001 §Consecuencias); solo afecta POD, FAR y CSI.
    """
    observed = {s.target_date: s.observed for s in history}
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


def _rf_metrics(
    model: CalibratedForest, variant: Variant, valid: list[Sample], test: list[Sample], n_bins: int
) -> list[ModelMetrics]:
    """RF calibrado y sin calibrar de una variante."""
    labels = {"variant": variant, "available_live": LIVE_NOTES[variant] is None}
    return [
        _model_metrics(
            "rf",
            (valid, model.validation_probs(valid, calibrated)),
            (test, model.predict(test, calibrated)),
            n_bins,
        ).model_copy(update={**labels, "calibrated": calibrated, "note": LIVE_NOTES[variant]})
        for calibrated in (True, False)
    ]


def _report(
    config: EvalConfig, test_start: date, metrics: list[ModelMetrics], daily: list[DailyOutcome]
) -> EvaluationReport:
    """Informe del contrato; `daily` es del RF operativo calibrado (`metrics[0]`)."""
    return EvaluationReport(
        test_period=TestPeriod(start=test_start, end=config.periods.test_end),
        target_rule=config.rule,
        threshold_mm=config.threshold_mm,
        data_plan=config.data_plan,
        scenarios=Scenarios(con_est_b=metrics, sin_est_b=[]),
        daily=daily,
        daily_variant="operativa",
        excluded_imputed_days=metrics[0].excluded_imputed_days,
    )


def run_evaluation(samples: Sequence[Sample], config: EvalConfig) -> EvaluationResult:
    """Ajusta el RF de cada variante, evalúa frente a las líneas base y arma el informe.

    Raises:
        ValueError: si no hay días en el periodo de prueba o faltan datos para ajustar.
    """
    parts = split_samples(samples, config.periods)
    if not parts["test"]:
        msg = "no hay días en el periodo de prueba"
        raise ValueError(msg)
    valid, test = _comparable(parts["valid"]), _comparable(parts["test"])
    models = {
        v: fit_forest(parts["train"], parts["valid"], config.rf, variant_columns(v))
        for v in VARIANTS
    }
    rf = [m for v in VARIANTS for m in _rf_metrics(models[v], v, valid, test, config.n_bins)]
    baselines = _baselines(parts["train"] + parts["valid"], valid, test, config)
    daily = _daily(test, models["operativa"].predict(test), rf[0].threshold)
    test_start = min(s.target_date for s in parts["test"])
    return EvaluationResult(_report(config, test_start, [*rf, *baselines], daily), models)
