"""Pronósticos precalculados que sirve `GET /forecast` (TASK-008 → TASK-015).

Se publica una emisión por día desde el inicio del periodo de prueba (para la
reproducción histórica) hasta el último día con datos (pronóstico vigente).
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from climapp.forecast.dataset import Sample
from climapp.forecast.features import FEATURE_NAMES
from climapp.forecast.model import CalibratedForest

ACCUM3_INDEX = FEATURE_NAMES.index("accum3_mean")


class ForecastRecord(BaseModel):
    """Pronóstico emitido al cierre del día `issue_date` para `target_date`."""

    issue_date: date
    target_date: date
    issued_at: datetime
    prob_ge_threshold: float
    accum_3d_mm: float | None
    accum_3d_level: Literal["normal", "elevado"]
    inputs_available: list[str]
    model_version: str


@dataclass(frozen=True, slots=True)
class PublishContext:
    """Datos de contexto para publicar las emisiones.

    Attributes:
        from_issue: primera fecha de emisión que se publica.
        tz: zona local; `issued_at` es la medianoche que cierra el día de emisión.
        accum3_threshold_mm: umbral del indicador de 3 días (`ACCUM3_THRESHOLD_MM`).
        model_version: hash de los datos y parámetros del modelo.
        inputs: series con dato por día de emisión.
    """

    from_issue: date
    tz: ZoneInfo
    accum3_threshold_mm: float
    model_version: str
    inputs: Mapping[date, list[str]]


def _record(sample: Sample, prob: float, ctx: PublishContext) -> ForecastRecord:
    """Pronóstico de una emisión."""
    accum = sample.x[ACCUM3_INDEX]
    accum_mm = None if math.isnan(accum) else round(accum, 1)
    elevated = accum_mm is not None and accum_mm >= ctx.accum3_threshold_mm
    return ForecastRecord(
        issue_date=sample.issue_date,
        target_date=sample.target_date,
        issued_at=datetime.combine(sample.issue_date + timedelta(days=1), time(0, 0), ctx.tz),
        prob_ge_threshold=prob,
        accum_3d_mm=accum_mm,
        accum_3d_level="elevado" if elevated else "normal",
        inputs_available=ctx.inputs.get(sample.issue_date, []),
        model_version=ctx.model_version,
    )


def forecast_records(
    samples: Sequence[Sample], model: CalibratedForest, ctx: PublishContext
) -> list[ForecastRecord]:
    """Emisiones desde `ctx.from_issue`, en orden de fecha."""
    chosen = sorted(
        (s for s in samples if s.issue_date >= ctx.from_issue), key=lambda s: s.issue_date
    )
    return [_record(s, p, ctx) for s, p in zip(chosen, model.predict(chosen), strict=True)]
