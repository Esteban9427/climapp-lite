"""Vistas web móviles: pronóstico, formulario de reporte y lista (TASK-017, ADR-005).

HTML renderizado en el servidor con Jinja2; HTMX envía el formulario y sondea el estado.
Reutiliza las mismas funciones que la API, así que la vista y el contrato no divergen.
El aviso "No es una alerta oficial" está en la plantilla base: aparece siempre.
"""

from datetime import date, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from climapp.api.deps import ApiError, NowDep, SettingsDep
from climapp.api.forecast_routes import ExplainerDep, forecast
from climapp.api.reports import MAX_TEXT_CHARS, MuseDep, StoreDep, post_report
from climapp.api.schemas import Forecast, Report
from climapp.config import Settings
from climapp.verification.basin import BasinError, load_basin
from climapp.web.demo import DemoReport, load_demo_reports
from climapp.web.map import map_view

TEMPLATES = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")
LIST_LIMIT = 20
router = APIRouter()


def _mm(value: float) -> str:
    """Milímetros con coma decimal y sin ",0" sobrante: 20 mm, 50,4 mm."""
    text = f"{value:.1f}".rstrip("0").rstrip(".")
    return f"{text.replace('.', ',')} mm"


def _local_time(value: datetime) -> str:
    """Hora observada en formato corto."""
    return value.strftime("%Y-%m-%d %H:%M")


TEMPLATES.env.filters["mm"] = _mm
TEMPLATES.env.filters["local_time"] = _local_time


def _base(settings: Settings) -> dict[str, object]:
    """Contexto común: los canales oficiales del aviso y la reproducción de la demo."""
    return {
        "official_url": settings.official_channels_url,
        "ideam_url": settings.ideam_alerts_url,
        "demo_replay_date": settings.demo_replay_date,
    }


def _demo_examples(settings: Settings) -> tuple[list[DemoReport], tuple[float, float] | None]:
    """Ejemplos de la demo y el centro de la cuenca; vacío fuera del modo fallback."""
    if not settings.demo_fallback:
        return [], None
    try:
        examples = load_demo_reports(settings.demo_reports_file)
        center = load_basin(settings.data_dir / settings.basin_polygon_file).center()
    except (OSError, ValueError, BasinError):
        return [], None
    return examples, center


def _forecast_or_error(
    settings: Settings, now: datetime, explainer: ExplainerDep, replay_date: date | None
) -> tuple[Forecast | None, str]:
    """Pronóstico para la vista, o el mensaje del estado de error."""
    try:
        return forecast(settings, now, explainer, replay_date=replay_date, variant=None), ""
    except ApiError as err:
        return None, err.message


@router.get("/", response_class=HTMLResponse)
def index(  # noqa: PLR0913 - dependencias de la vista
    *,
    request: Request,
    settings: SettingsDep,
    now: NowDep,
    explainer: ExplainerDep,
    store: StoreDep,
    replay_date: date | None = None,
) -> HTMLResponse:
    """Página principal: pronóstico, formulario y reportes verificados."""
    shown, error = _forecast_or_error(settings, now, explainer, replay_date)
    records = store.list("verificado", None, None, LIST_LIMIT)
    reports = [r.summary(settings.public_coord_decimals) for r in records]
    context = _base(settings) | {
        "forecast": shown,
        "forecast_error": error,
        "replay_date": replay_date,
        "reports": reports,
    }
    examples, center = _demo_examples(settings)
    context |= {"demo_examples": examples, "demo_center": center}
    return TEMPLATES.TemplateResponse(request, "index.html", context)


def _status(request: Request, report: Report | None, error: str = "") -> HTMLResponse:
    """Fragmento con el estado del reporte (o un error)."""
    context = {"report": report, "error": error}
    return TEMPLATES.TemplateResponse(request, "partials/report_status.html", context)


@router.post("/web/reports", response_class=HTMLResponse)
async def web_post_report(  # noqa: PLR0913 - campos del formulario
    *,
    request: Request,
    background: BackgroundTasks,
    settings: SettingsDep,
    now: NowDep,
    client: MuseDep,
    store: StoreDep,
    lat: Annotated[float, Form(ge=-90, le=90)],
    lon: Annotated[float, Form(ge=-180, le=180)],
    text: Annotated[str | None, Form(max_length=MAX_TEXT_CHARS)] = None,
    photo: Annotated[UploadFile | None, File()] = None,
) -> HTMLResponse:
    """Envía el formulario por la misma ruta de la API y devuelve el estado inicial."""
    if photo is not None and not photo.filename:
        photo = None  # campo de archivo vacío en el formulario
    try:
        report = await post_report(
            background=background,
            settings=settings,
            now=now,
            client=client,
            store=store,
            lat=lat,
            lon=lon,
            text=text or None,
            photo=photo,
        )
    except ApiError as err:
        return _status(request, None, f"{err.message[:1].upper()}{err.message[1:]}.")
    return _status(request, report)


@router.get("/web/reports/{report_id}/estado", response_class=HTMLResponse)
def web_report_status(
    request: Request, report_id: UUID, settings: SettingsDep, store: StoreDep
) -> HTMLResponse:
    """Estado actual del reporte; el sondeo se detiene en un estado final."""
    record = store.get(report_id)
    if record is None:
        return _status(request, None, "No se pudo consultar el estado; reintenta.")
    return _status(request, record.public(settings.public_coord_decimals))


@router.get("/mapa", response_class=HTMLResponse)
def mapa(
    request: Request,
    settings: SettingsDep,
    now: NowDep,
    store: StoreDep,
    replay_date: date | None = None,
) -> HTMLResponse:
    """Mapa de reportes verificados del día con el resultado del pronóstico."""
    view = map_view(settings, store, now, replay_date)
    data = {
        "markers": view.markers,
        "center": view.center,
        "tile_url": settings.map_tile_url,
        "attribution": settings.map_attribution,
        "attribution_url": settings.map_attribution_url,
    }
    context = _base(settings) | {
        "view": view,
        "replay_date": replay_date,
        "map_data": data,
        "attribution": settings.map_attribution,
        "attribution_url": settings.map_attribution_url,
    }
    return TEMPLATES.TemplateResponse(request, "mapa.html", context)
