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
from climapp.api.reports import evidence_sources
from climapp.api.schemas import ReportSummary
from climapp.api.store import ReportStore
from climapp.config import Settings
from climapp.verification.basin import BasinError, load_basin
from climapp.verification.evidence import EvidenceSources
from climapp.web.agreement import AgreementThresholds, agreement_label
from climapp.web.report_view import event_title, evidence_rows

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
    basin: list[list[list[float]]]


def _outcome(settings: Settings, target: date) -> str | None:
    """Resultado del pronóstico para el día objetivo, o `None` si aún no hay."""
    try:
        report = load_evaluation(settings.data_dir / settings.evaluation_file)
    except (ArtifactMissingError, ArtifactInvalidError):
        return None
    found = [d.outcome for d in report.daily if d.date == target]
    return OUTCOME_TEXT.get(found[0]) if found else None


@dataclass(frozen=True, slots=True)
class _MarkerContext:
    """Lo que necesita cada marcador: día, zona horaria, cortes y artefactos."""

    day: date
    tz: ZoneInfo
    thresholds: AgreementThresholds
    sources: EvidenceSources


def _marker(report: ReportSummary, ctx: _MarkerContext) -> dict[str, object] | None:
    """Marcador de un reporte verificado observado en `ctx.day`; `None` si no corresponde."""
    if report.observed_at is None or report.confidence is None:
        return None
    if report.observed_at.astimezone(ctx.tz).date() != ctx.day:
        return None
    score = round(report.confidence.score * PERCENT)
    agreement = agreement_label(report.confidence.score, ctx.thresholds).text
    title = event_title(report.event_type, report.intensity)
    label = f"{title} · {agreement} · confianza {score} %"
    details = evidence_rows(report.confidence, ctx.sources.day_values(ctx.day))
    return {"lat": report.lat, "lon": report.lon, "label": label, "details": details}


def _center_and_outline(settings: Settings) -> tuple[list[float] | None, list[list[list[float]]]]:
    """Centro y anillos exteriores `[lat, lon]` del polígono provisional, si existe."""
    try:
        basin = load_basin(settings.data_dir / settings.basin_polygon_file)
    except BasinError:
        return None, []
    outline = [[[lat, lon] for lon, lat in outer] for outer, *_ in basin.polygons]
    return list(basin.center()), outline


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
    ctx = _MarkerContext(
        day,
        settings.local_timezone,
        AgreementThresholds.from_settings(settings),
        evidence_sources(settings),
    )
    markers = [m for m in (_marker(r, ctx) for r in public) if m is not None]
    center, outline = _center_and_outline(settings)
    return MapView(day, target, _outcome(settings, target), markers, center, outline)
