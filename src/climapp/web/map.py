"""Mapa mínimo de reportes verificados con Leaflet y OpenStreetMap (TASK-018).

Marcadores: reportes verificados observados el día mostrado, con coordenadas ya
redondeadas. En la reproducción, ese día es el día objetivo, el mismo que evalúa la
leyenda; en vivo, es hoy. Leyenda: el resultado del pronóstico para el día objetivo
según `GET /evaluation` (`daily`).
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from climapp.api.artifacts import ArtifactInvalidError, ArtifactMissingError, load_evaluation
from climapp.api.schemas import ReportSummary
from climapp.api.store import ReportStore
from climapp.config import Settings
from climapp.verification.basin import BasinError, load_basin
from climapp.web.agreement import AgreementThresholds, agreement_label

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


def _marker(
    report: ReportSummary, day: date, tz: ZoneInfo, thresholds: AgreementThresholds
) -> dict[str, object] | None:
    """Marcador de un reporte verificado observado en `day`; `None` si no corresponde."""
    if report.observed_at is None or report.confidence is None:
        return None
    if report.observed_at.astimezone(tz).date() != day:
        return None
    score = round(report.confidence.score * PERCENT)
    agreement = agreement_label(report.confidence.score, thresholds).text
    label = f"{report.event_type} {report.intensity} · {agreement} · confianza {score} %"
    return {"lat": report.lat, "lon": report.lon, "label": label}


def _center(settings: Settings) -> list[float] | None:
    """Centro de la cuenca, si el polígono existe."""
    try:
        return list(load_basin(settings.data_dir / settings.basin_polygon_file).center())
    except BasinError:
        return None


def map_view(settings: Settings, store: ReportStore, now: datetime, replay: date | None) -> MapView:
    """Arma la vista: día, resultado del objetivo, marcadores y centro.

    En la reproducción (`replay` = día de emisión) los reportes son los del día objetivo;
    en vivo, los de hoy, porque el día objetivo (mañana) todavía no tiene reportes.
    """
    issue = replay or now.astimezone(settings.local_timezone).date()
    target = issue + timedelta(days=1)
    day = target if replay else issue
    verified = store.list("verificado", None, None, MAP_LIST_LIMIT)
    public = (r.summary(settings.public_coord_decimals) for r in verified)
    thresholds = AgreementThresholds.from_settings(settings)
    candidates = (_marker(r, day, settings.local_timezone, thresholds) for r in public)
    markers = [m for m in candidates if m is not None]
    return MapView(day, target, _outcome(settings, target), markers, _center(settings))
