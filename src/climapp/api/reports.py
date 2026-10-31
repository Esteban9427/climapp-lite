"""Rutas de reportes ciudadanos: `POST /reports`, `GET /reports` y `GET /reports/{id}`.

`POST` responde `202` enseguida: la verificación (compuerta y confianza) corre en segundo
plano y el cliente sondea `GET /reports/{id}`. Fuera de la cuenca se rechaza sin llamar
al LLM. La foto se guarda sin metadatos y nunca se publica el texto del ciudadano. La
lista no lleva id ni afirmaciones; el detalle por id (UUID4) lo ve quien envió el reporte.
"""

from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile

from climapp.api.deps import ApiError, NowDep, SettingsDep
from climapp.api.photos import PhotoError, strip_metadata
from climapp.api.schemas import (
    RejectReason,
    Report,
    ReportRecord,
    ReportStatus,
    ReportSummary,
)
from climapp.api.store import ReportStore
from climapp.config import Settings
from climapp.logging import get_logger
from climapp.verification.basin import BasinError, load_basin
from climapp.verification.confidence import ConfidenceWeights, load_station_groups
from climapp.verification.evidence import EvidenceSources
from climapp.verification.muse import MuseClient, build_client
from climapp.verification.reports import ReportVerifier

log = get_logger(__name__)
router = APIRouter()
MAX_TEXT_CHARS = 1000  # data-model ReportIn
LIST_LIMIT_MAX = 500
LIST_LIMIT_DEFAULT = 100
_CLIENTS: dict[int, tuple[Settings, MuseClient]] = {}


def get_muse_client(settings: SettingsDep) -> MuseClient:
    """Cliente Muse (real o grabado según `DEMO_FALLBACK`), uno por configuración."""
    cached = _CLIENTS.get(id(settings))
    if cached is None or cached[0] is not settings:
        cached = (settings, build_client(settings))
        _CLIENTS[id(settings)] = cached
    return cached[1]


def get_store(settings: SettingsDep) -> ReportStore:
    """Almacén SQLite en `DATA_DIR/REPORTS_DB_FILE`."""
    return ReportStore(settings.data_dir / settings.reports_db_file, settings.local_timezone)


MuseDep = Annotated[MuseClient, Depends(get_muse_client)]
StoreDep = Annotated[ReportStore, Depends(get_store)]


def _verifier(settings: Settings, client: MuseClient) -> ReportVerifier:
    """Verificador con los artefactos y pesos de la configuración."""
    data = settings.data_dir
    sources = EvidenceSources(
        data / settings.daily_stations_file,
        data / settings.forecasts_file,
        data / settings.evaluation_file,
        settings.local_timezone,
    )
    try:
        groups = load_station_groups(data / settings.station_groups_file)
    except (OSError, ValueError, KeyError) as err:
        log.warning("report.groups_missing", error=type(err).__name__)
        groups = ()
    weights = ConfidenceWeights.from_settings(settings)
    return ReportVerifier(client, sources, groups, weights, settings.verify_max_attempts)


def _verify_in_background(store: ReportStore, verifier: ReportVerifier, report_id: UUID) -> None:
    """Tarea en segundo plano: verifica y guarda el resultado."""
    record = store.get(report_id)
    if record is not None:
        store.update(verifier.verify(record))


async def _clean_photo(photo: UploadFile | None, settings: Settings) -> tuple[bytes, str] | None:
    """Foto sin metadatos, o `None` si no se envió."""
    if photo is None:
        return None
    try:
        return strip_metadata(await photo.read(), settings.max_photo_bytes)
    except PhotoError as err:
        raise ApiError(422, "entrada_invalida", str(err)) from err


def _inside_basin(settings: Settings, lat: float, lon: float) -> bool:
    """`True` si el punto cae en la cuenca; 503 si falta el polígono."""
    try:
        return load_basin(settings.data_dir / settings.basin_polygon_file).contains(lat, lon)
    except BasinError as err:
        raise ApiError(503, "sin_poligono", str(err)) from err


def _new_record(lat: float, lon: float, text: str | None, now: datetime) -> ReportRecord:
    """Reporte recién recibido, en estado `verificando`."""
    return ReportRecord(
        id=uuid4(),
        received_at=now.astimezone(UTC),
        lat=lat,
        lon=lon,
        status="verificando",
        reject_reason=None,
        structured=None,
        confidence=None,
        attempts=[],
        fallback=False,
        text=text,
        photo_file=None,
    )


def _rejected(record: ReportRecord, reason: RejectReason) -> ReportRecord:
    """Reporte rechazado sin pasar por el LLM."""
    return record.model_copy(update={"status": "rechazado", "reject_reason": reason})


def _save_photo(settings: Settings, record: ReportRecord, photo: tuple[bytes, str]) -> ReportRecord:
    """Guarda la foto limpia como `PHOTOS_DIR/<id>.<ext>`."""
    folder = settings.data_dir / settings.photos_dir
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{record.id}.{photo[1]}"
    (folder / name).write_bytes(photo[0])
    return record.model_copy(update={"photo_file": name})


@router.post("/reports", status_code=202, response_model=Report)
async def post_report(  # noqa: PLR0913 - campos del formulario del contrato (ReportIn)
    *,
    background: BackgroundTasks,
    settings: SettingsDep,
    now: NowDep,
    client: MuseDep,
    store: StoreDep,
    lat: Annotated[float, Form(ge=-90, le=90)],
    lon: Annotated[float, Form(ge=-180, le=180)],
    text: Annotated[str | None, Form(min_length=1, max_length=MAX_TEXT_CHARS)] = None,
    photo: Annotated[UploadFile | None, File()] = None,
) -> Report:
    """`POST /reports`: recibe el reporte y lo verifica en segundo plano.

    Raises:
        ApiError: 422 sin texto ni foto o con foto inválida; 503 sin polígono de la cuenca.
    """
    if not text and photo is None:
        raise ApiError(422, "entrada_invalida", "envía un texto o una foto")
    clean = await _clean_photo(photo, settings)
    record = _new_record(lat, lon, text, now)
    if not _inside_basin(settings, lat, lon):
        record = _rejected(record, "fuera_de_cuenca")
        store.add(record)
        return record.public(settings.public_coord_decimals)
    if clean is not None:
        record = _save_photo(settings, record, clean)
    store.add(record)
    background.add_task(_verify_in_background, store, _verifier(settings, client), record.id)
    log.info("report.received", report_id=str(record.id), photo=clean is not None)
    return record.public(settings.public_coord_decimals)


@router.get("/reports", response_model=list[ReportSummary])
def list_reports(  # noqa: PLR0913 - parámetros de consulta del contrato
    *,
    settings: SettingsDep,
    store: StoreDep,
    status: ReportStatus | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=LIST_LIMIT_MAX)] = LIST_LIMIT_DEFAULT,
) -> list[ReportSummary]:
    """`GET /reports`: lista sin id ni afirmaciones, con coordenadas redondeadas."""
    records = store.list(status, date_from, date_to, limit)
    return [r.summary(settings.public_coord_decimals) for r in records]


@router.get("/reports/{report_id}", response_model=Report)
def get_report(report_id: UUID, settings: SettingsDep, store: StoreDep) -> Report:
    """`GET /reports/{id}`: estado de un reporte (sondeo).

    Raises:
        ApiError: 404 si no existe.
    """
    record = store.get(report_id)
    if record is None:
        raise ApiError(404, "reporte_no_encontrado", "no existe un reporte con ese id")
    return record.public(settings.public_coord_decimals)
