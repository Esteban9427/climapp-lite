"""Mapa mínimo de reportes verificados con Leaflet y OpenStreetMap (TASK-018).

Marcadores: reportes verificados observados el día mostrado (la fecha de emisión en la
reproducción, hoy en vivo), con coordenadas ya redondeadas. Leyenda: el resultado del
pronóstico para el día objetivo según `GET /evaluation` (`daily`).
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from climapp.api.artifacts import ArtifactInvalidError, ArtifactMissingError, load_evaluation
from climapp.api.schemas import Report
from climapp.api.store import ReportStore
from climapp.config import Settings
from climapp.verification.basin import BasinError, load_basin

OUTCOME_TEXT = {
    "acierto": "acierto",
    "falsa_alarma": "falsa alarma",
    "fallo": "fallo (no se pronosticó el evento)",
    "correcto_negativo": "correcto negativo",
}
PERCENT = 100
MAP_LIST_LIMIT = 500


@dataclass(frozen=True, slots=True)
class MapView:
    """Datos de la vista del mapa."""

    day: date
    target_day: date
    outcome: str | None
    markers: list[dict[str, object]]
    center: list[float] | None


def _outcome(settings: Settings, target: date) -> str | None:
    """Resultado del pronóstico para el día objetivo, o `None` si aún no hay."""
    try:
        report = load_evaluation(settings.data_dir / settings.evaluation_file)
    except (ArtifactMissingError, ArtifactInvalidError):
        return None
    found = [d.outcome for d in report.daily if d.date == target]
    return OUTCOME_TEXT.get(found[0]) if found else None


def _marker(report: Report, day: date, tz: ZoneInfo) -> dict[str, object] | None:
    """Marcador de un reporte verificado observado en `day`; `None` si no corresponde."""
    structured, confidence = report.structured, report.confidence
    if structured is None or confidence is None:
        return None
    if structured.observed_at.astimezone(tz).date() != day:
        return None
    score = round(confidence.score * PERCENT)
    label = f"{structured.event_type} {structured.intensity} · confianza {score} %"
    return {"lat": report.lat, "lon": report.lon, "label": label}


def _center(settings: Settings) -> list[float] | None:
    """Centro de la cuenca, si el polígono existe."""
    try:
        return list(load_basin(settings.data_dir / settings.basin_polygon_file).center())
    except BasinError:
        return None


def map_view(settings: Settings, store: ReportStore, now: datetime, replay: date | None) -> MapView:
    """Arma la vista: día, resultado del objetivo, marcadores y centro."""
    day = replay or now.astimezone(settings.local_timezone).date()
    target = day + timedelta(days=1)
    verified = store.list("verificado", None, None, MAP_LIST_LIMIT)
    public = (r.public(settings.public_coord_decimals) for r in verified)
    candidates = (_marker(r, day, settings.local_timezone) for r in public)
    markers = [m for m in candidates if m is not None]
    return MapView(day, target, _outcome(settings, target), markers, _center(settings))
