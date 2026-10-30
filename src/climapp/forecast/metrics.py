"""Métricas de verificación del pronóstico (ADR-001 §10).

Alerta = probabilidad ≥ umbral de decisión, que se fija en validación y nunca en
prueba. Los días imputados o sin observación no entran (ADR-004 §3).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel


@dataclass(frozen=True, slots=True)
class EvalRecord:
    """Un día evaluable: probabilidad emitida y lo observado."""

    date: date
    prob: float
    observed: bool | None
    imputed: bool


class ReliabilityBin(BaseModel):
    """Una barra de la curva de calibración."""

    bin: str
    forecast: float
    observed: float
    n: int


class ModelMetrics(BaseModel):
    """Métricas de un modelo (`ModelMetrics` de `docs/openapi.yaml`).

    `variant`, `calibrated`, `available_live` y `note` solo aplican al RF.
    """

    name: str
    variant: str | None = None
    calibrated: bool | None = None
    available_live: bool | None = None
    note: str | None = None
    pod: float
    far: float
    csi: float
    brier: float
    auc: float
    reliability: list[ReliabilityBin]
    threshold: float
    n_days: int
    excluded_imputed_days: int


def contingency(
    obs: Sequence[bool], probs: Sequence[float], threshold: float
) -> tuple[int, int, int, int]:
    """Tabla de contingencia `(aciertos, fallos, falsas alarmas, correctos negativos)`."""
    alerts = [p >= threshold for p in probs]
    hits = sum(a and o for a, o in zip(alerts, obs, strict=True))
    misses = sum(o and not a for a, o in zip(alerts, obs, strict=True))
    false_alarms = sum(a and not o for a, o in zip(alerts, obs, strict=True))
    return hits, misses, false_alarms, len(obs) - hits - misses - false_alarms


def brier(obs: Sequence[bool], probs: Sequence[float]) -> float:
    """Error cuadrático medio de la probabilidad (0 es perfecto)."""
    return sum((p - o) ** 2 for p, o in zip(probs, obs, strict=True)) / len(obs)


def auc(obs: Sequence[bool], probs: Sequence[float]) -> float:
    """Área bajo la curva ROC (Mann-Whitney; los empates cuentan 0,5).

    Raises:
        ValueError: si falta alguna de las dos clases.
    """
    pos = sorted(p for p, o in zip(probs, obs, strict=True) if o)
    neg = sorted(p for p, o in zip(probs, obs, strict=True) if not o)
    if not pos or not neg:
        msg = "el AUC necesita ambas clases"
        raise ValueError(msg)
    ranks = _midranks([*pos, *neg])
    rank_sum = sum(ranks[p] for p in pos)
    return (rank_sum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def _midranks(values: Sequence[float]) -> dict[float, float]:
    """Rango medio (desde 1) de cada valor distinto."""
    ordered = sorted(values)
    ranks: dict[float, float] = {}
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and ordered[j + 1] == ordered[i]:
            j += 1
        ranks[ordered[i]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def reliability(obs: Sequence[bool], probs: Sequence[float], n_bins: int) -> list[ReliabilityBin]:
    """Curva de calibración en `n_bins` intervalos iguales; solo los que tienen días."""
    groups: dict[int, list[tuple[float, bool]]] = {}
    for p, o in zip(probs, obs, strict=True):
        groups.setdefault(min(int(p * n_bins), n_bins - 1), []).append((p, o))
    return [
        ReliabilityBin(
            bin=f"{k / n_bins:.1f}-{(k + 1) / n_bins:.1f}",
            forecast=sum(p for p, _ in g) / len(g),
            observed=sum(o for _, o in g) / len(g),
            n=len(g),
        )
        for k, g in sorted(groups.items())
    ]


def _csi(obs: Sequence[bool], probs: Sequence[float], threshold: float) -> float:
    """CSI = aciertos / (aciertos + fallos + falsas alarmas); 0 si no hay ninguno."""
    hits, misses, false_alarms, _ = contingency(obs, probs, threshold)
    total = hits + misses + false_alarms
    return hits / total if total else 0.0


def best_threshold(obs: Sequence[bool], probs: Sequence[float]) -> float:
    """Umbral de decisión que maximiza el CSI (se usa solo sobre validación)."""
    return max(sorted(set(probs)), key=lambda t: _csi(obs, probs, t))


def evaluate(
    records: Sequence[EvalRecord], name: str, threshold: float, n_bins: int
) -> ModelMetrics:
    """Calcula las métricas de un modelo sin días imputados ni sin observación.

    Raises:
        ValueError: si no quedan eventos observados (POD indefinido) o falta una clase.
    """
    kept = [r for r in records if not r.imputed and r.observed is not None]
    obs = [bool(r.observed) for r in kept]
    probs = [r.prob for r in kept]
    hits, misses, false_alarms, _ = contingency(obs, probs, threshold)
    if hits + misses == 0:
        msg = "no hay eventos observados para calcular el POD"
        raise ValueError(msg)
    return ModelMetrics(
        name=name,
        pod=hits / (hits + misses),
        far=false_alarms / (hits + false_alarms) if hits + false_alarms else 0.0,
        csi=hits / (hits + misses + false_alarms),
        brier=brier(obs, probs),
        auc=auc(obs, probs),
        reliability=reliability(obs, probs, n_bins),
        threshold=threshold,
        n_days=len(kept),
        excluded_imputed_days=sum(r.imputed for r in records),
    )
