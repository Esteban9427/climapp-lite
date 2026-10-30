"""Lectura de los artefactos precalculados por `climapp-train` (ADR-001)."""

import json
from datetime import date
from pathlib import Path

from pydantic import TypeAdapter

from climapp.forecast.evaluation import EvaluationReport
from climapp.forecast.features import Variant
from climapp.forecast.publish import ForecastRecord

_RECORDS = TypeAdapter(list[ForecastRecord])


class ArtifactMissingError(LookupError):
    """No existe el artefacto o el pronóstico pedido."""


def _read(path: Path) -> str:
    """Texto del artefacto; `ArtifactMissingError` si no existe."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as err:
        msg = f"no existe {path.name}"
        raise ArtifactMissingError(msg) from err


def find_forecast(path: Path, variant: Variant, issue_date: date | None) -> ForecastRecord:
    """Pronóstico de la variante: el de `issue_date` o, si es `None`, el más reciente.

    Raises:
        ArtifactMissingError: si no hay artefacto o no hay pronóstico para esa fecha.
    """
    records = [r for r in _RECORDS.validate_json(_read(path)) if r.variant == variant]
    if issue_date is not None:
        records = [r for r in records if r.issue_date == issue_date]
    if not records:
        msg = f"sin pronóstico {variant} para {issue_date or 'la fecha vigente'}"
        raise ArtifactMissingError(msg)
    return max(records, key=lambda r: r.issue_date)


def load_evaluation(path: Path) -> EvaluationReport:
    """Informe de evaluación precalculado.

    Raises:
        ArtifactMissingError: si no existe.
    """
    return EvaluationReport.model_validate(json.loads(_read(path)))
