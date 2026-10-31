"""Modelos de respuesta de la API (`docs/openapi.yaml`)."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from climapp.config import DataPlan, TargetRule
from climapp.forecast.features import Variant


class Error(BaseModel):
    """Formato único de error `{code, message}` (`docs/api-contracts.md`)."""

    code: str
    message: str


class Forecast(BaseModel):
    """Pronóstico para mañana (`Forecast` de `docs/openapi.yaml`)."""

    issued_at: datetime
    target_date: date
    prob_ge_threshold: float
    threshold_mm: float
    target_rule: TargetRule
    accum_3d_mm: float | None
    accum_3d_level: Literal["normal", "elevado"]
    data_plan: DataPlan
    variant: Variant
    model_version: str
    explanation: str | None
    explanation_fallback: bool
    inputs_available: list[str]
    stale: bool
    replay: bool
    disclaimer: str
    official_channels_url: str
