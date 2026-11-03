"""Lectura de los artefactos precalculados por `climapp-train` (ADR-001)."""

import json
from datetime import date
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from climapp.api.schemas import ReportVerificationEval
from climapp.forecast.evaluation import EvaluationReport
from climapp.forecast.features import Variant
from climapp.forecast.publish import ForecastRecord
from climapp.logging import get_logger

log = get_logger(__name__)
_RECORDS = TypeAdapter(list[ForecastRecord])


class ArtifactMissingError(LookupError):
    """No existe el artefacto o el pronóstico pedido."""


class ArtifactInvalidError(ValueError):
    """El artefacto existe pero no es JSON válido o no cumple su modelo."""


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
        ArtifactInvalidError: si el artefacto está corrupto.
    """
    try:
        loaded = _RECORDS.validate_json(_read(path))
    except ValidationError as err:
        raise ArtifactInvalidError(f"{path.name} no es válido") from err
    records = [r for r in loaded if r.variant == variant]
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
        ArtifactInvalidError: si está corrupto.
    """
    try:
        return EvaluationReport.model_validate(json.loads(_read(path)))
    except (json.JSONDecodeError, ValidationError) as err:
        raise ArtifactInvalidError(f"{path.name} no es válido") from err


def load_report_eval(path: Path) -> ReportVerificationEval | None:
    """Resumen de la evaluación de reportes (TASK-021/036), o `None` si falta o es inválido.

    No lanza: sin resumen, `GET /evaluation` sigue publicando la evaluación del pronóstico.
    """
    try:
        return ReportVerificationEval.model_validate(json.loads(_read(path)))
    except ArtifactMissingError:
        log.warning("evaluation.report_eval_missing", path=path.name)
    except OSError as err:  # directorio, permisos: tampoco es un 500 (revisión de Muse)
        log.warning("evaluation.report_eval_unreadable", path=path.name, error=type(err).__name__)
    except (json.JSONDecodeError, ValidationError) as err:
        log.warning("evaluation.report_eval_invalid", path=path.name, error=type(err).__name__)
    return None
