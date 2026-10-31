"""Modelos de respuesta de la API (`docs/openapi.yaml`)."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from climapp.config import DataPlan, TargetRule
from climapp.forecast.features import Variant
from climapp.verification.checks import Reason
from climapp.verification.confidence import Confidence
from climapp.verification.schemas import EventType, Intensity, ReportStructured

ReportStatus = Literal["verificando", "verificado", "rechazado", "requiere_revision_humana"]
RejectReason = Literal["fuera_de_cuenca", "entrada_invalida"]


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


class VerificationAttemptOut(BaseModel):
    """Intento de verificación publicado (`VerificationAttempt` de `docs/openapi.yaml`)."""

    model_config = ConfigDict(frozen=True)

    n: int = Field(ge=1)
    passed: bool
    reasons: list[Reason]
    finish_reason: str
    tokens_in: int
    tokens_out: int
    latency_ms: int


class Report(BaseModel):
    """Reporte publicado (`Report` de `docs/openapi.yaml`); sin el texto del ciudadano."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    received_at: datetime
    lat: float
    lon: float
    status: ReportStatus
    reject_reason: RejectReason | None
    structured: ReportStructured | None
    confidence: Confidence | None
    attempts: list[VerificationAttemptOut]
    fallback: bool


class ReportSummary(BaseModel):
    """Reporte para la lista y el mapa (`ReportSummary`): sin id, texto ni afirmaciones."""

    model_config = ConfigDict(frozen=True)

    event_type: EventType | None
    intensity: Intensity | None
    observed_at: datetime | None
    lat: float
    lon: float
    status: ReportStatus
    confidence: Confidence | None
    fallback: bool


class ReportRecord(Report):
    """Reporte guardado: además del público, el texto y la foto limpia (privados)."""

    text: str | None
    photo_file: str | None

    def public(self, decimals: int) -> Report:
        """Versión publicable: coordenadas redondeadas y sin texto ni foto."""
        data = self.model_dump(exclude={"text", "photo_file"})
        data |= {"lat": round(self.lat, decimals), "lon": round(self.lon, decimals)}
        return Report.model_validate(data)

    def summary(self, decimals: int) -> ReportSummary:
        """Versión para la lista y el mapa: solo campos estructurados y coordenadas redondeadas."""
        structured = self.structured
        return ReportSummary(
            event_type=structured.event_type if structured else None,
            intensity=structured.intensity if structured else None,
            observed_at=structured.observed_at if structured else None,
            lat=round(self.lat, decimals),
            lon=round(self.lon, decimals),
            status=self.status,
            confidence=self.confidence,
            fallback=self.fallback,
        )
