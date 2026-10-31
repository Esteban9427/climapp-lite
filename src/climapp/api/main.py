"""API de ClimApp Lite (`docs/openapi.yaml`). No es una alerta oficial.

Uso: `uv run uvicorn climapp.api.main:app`.
"""

from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from climapp.api.artifacts import (
    ArtifactInvalidError,
    ArtifactMissingError,
    find_forecast,
    load_evaluation,
)
from climapp.api.deps import ApiError, NowDep, SettingsDep, get_now, get_settings
from climapp.api.reports import router as reports_router
from climapp.api.schemas import Error, Forecast
from climapp.config import Settings, TargetRule
from climapp.forecast.evaluation import EvaluationReport
from climapp.forecast.features import Variant
from climapp.forecast.publish import ForecastRecord
from climapp.logging import get_logger
from climapp.verification.explain import Explainer, build_explainer

log = get_logger(__name__)
__all__ = ["ApiError", "create_app", "get_now", "get_settings"]
DISCLAIMER = (
    "No es una alerta oficial. ClimApp Lite es un pronóstico experimental e informativo: "
    "ante cualquier riesgo, sigue las indicaciones de los organismos oficiales."
)


def disclaimer_text(settings: Settings) -> str:
    """Aviso completo: no es alerta oficial y a qué canales oficiales acudir.

    Canal principal: `OFFICIAL_CHANNELS_URL` (gestión del riesgo de Cali); segundo canal:
    `IDEAM_ALERTS_URL` (pronósticos y alertas del IDEAM). Decisión del equipo, 2026-10-31.
    """
    ideam = f"los pronósticos y alertas del IDEAM ({settings.ideam_alerts_url})"
    if settings.official_channels_url:
        local = f"la Gestión del Riesgo de Cali ({settings.official_channels_url})"
        return f"{DISCLAIMER} Canales oficiales: {local} y {ideam}."
    return f"{DISCLAIMER} Canal oficial: {ideam}."


STALE_AFTER = timedelta(hours=24)  # contrato: stale si issued_at tiene más de 24 h
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    422: {"model": Error},
    503: {"model": Error},
}


_EXPLAINERS: dict[int, tuple[Settings, Explainer | None]] = {}


def get_explainer(settings: SettingsDep) -> Explainer | None:
    """Explicador de Muse (TASK-022), uno por configuración; `None` si no está habilitado.

    Depende de `get_settings`, así que respeta la configuración que reemplazan los tests.
    """
    cached = _EXPLAINERS.get(id(settings))
    if cached is None or cached[0] is not settings:
        cached = (settings, build_explainer(settings))
        _EXPLAINERS[id(settings)] = cached
    return cached[1]


ExplainerDep = Annotated[Explainer | None, Depends(get_explainer)]


def _to_forecast(
    record: ForecastRecord, settings: Settings, now: datetime, replay: bool
) -> Forecast:
    """Respuesta del contrato a partir del artefacto, con el aviso siempre presente."""
    return Forecast(
        **record.model_dump(include={"issued_at", "target_date", "prob_ge_threshold"}),
        **record.model_dump(include={"accum_3d_mm", "accum_3d_level", "variant"}),
        **record.model_dump(include={"model_version", "inputs_available"}),
        threshold_mm=settings.forecast_threshold_mm,
        target_rule=settings.target_rule,
        data_plan=settings.data_plan,
        explanation=None,  # se completa solo si pasa la compuerta (TASK-022)
        explanation_fallback=False,
        stale=now - record.issued_at > STALE_AFTER,
        replay=replay,
        disclaimer=disclaimer_text(settings),
        official_channels_url=settings.official_channels_url,
    )


def _explained(forecast: Forecast, explainer: Explainer | None) -> Forecast:
    """Agrega la explicación verificada, si el explicador está habilitado y pasó."""
    verified = explainer(forecast) if explainer else None
    if verified is None:
        return forecast
    update = {"explanation": verified.text, "explanation_fallback": verified.fallback}
    return forecast.model_copy(update=update)


def forecast(
    settings: SettingsDep,
    now: NowDep,
    explainer: ExplainerDep,
    replay_date: date | None = None,
    variant: Annotated[Variant | None, Query()] = None,
) -> Forecast:
    """`GET /forecast`: vigente (`operativa`) o reproducción histórica (`historica`).

    Args:
        settings: configuración (dependencia).
        now: instante actual (dependencia), para `stale`.
        explainer: explicador verificado (dependencia, TASK-022).
        replay_date: fecha de emisión a reproducir (solo demo).
        variant: variante pedida; por defecto según `replay_date` (ADR-001 §3).

    Returns:
        El pronóstico con el aviso y el enlace oficial.

    Raises:
        ApiError: 422 si se pide `historica` sin `replay_date`; 503 sin pronóstico.
    """
    chosen: Variant = variant or ("historica" if replay_date else "operativa")
    if chosen == "historica" and replay_date is None:
        raise ApiError(
            422, "variante_no_disponible", "la variante histórica solo existe en reproducción"
        )
    try:
        record = find_forecast(settings.data_dir / settings.forecasts_file, chosen, replay_date)
    except ArtifactMissingError as err:
        raise ApiError(503, "sin_pronostico", str(err)) from err
    except ArtifactInvalidError as err:
        raise ApiError(503, "artefacto_invalido", str(err)) from err
    built = _to_forecast(record, settings, now, replay=replay_date is not None)
    return _explained(built, explainer)


def evaluation(settings: SettingsDep, target_rule: TargetRule | None = None) -> EvaluationReport:
    """`GET /evaluation`: métricas del RF y de las líneas base en el periodo apartado.

    Args:
        settings: configuración (dependencia).
        target_rule: regla pedida; por defecto `TARGET_RULE`.

    Returns:
        El informe precalculado por `climapp-train`.

    Raises:
        ApiError: 503 sin informe válido; 422 si la regla pedida no se evaluó.
    """
    try:
        report = load_evaluation(settings.data_dir / settings.evaluation_file)
    except ArtifactMissingError as err:
        raise ApiError(503, "sin_evaluacion", str(err)) from err
    except ArtifactInvalidError as err:
        raise ApiError(503, "artefacto_invalido", str(err)) from err
    if (target_rule or settings.target_rule) != report.target_rule:
        raise ApiError(422, "regla_no_evaluada", f"solo se evaluó {report.target_rule}")
    return report


async def _api_error(_: Request, exc: Exception) -> JSONResponse:
    """Respuesta `{code, message}` de un `ApiError`."""
    if not isinstance(exc, ApiError):
        raise exc
    log.info("api.error", status=exc.status, code=exc.code)
    return JSONResponse(Error(code=exc.code, message=exc.message).model_dump(), exc.status)


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    """Parámetros inválidos: 422 con el formato del contrato, sin trazas."""
    if not isinstance(exc, RequestValidationError):
        raise exc
    fields = ", ".join(str(e["loc"][-1]) for e in exc.errors())
    return JSONResponse(
        Error(code="entrada_invalida", message=f"revisa: {fields}").model_dump(), 422
    )


def create_app() -> FastAPI:
    """Crea la aplicación con sus rutas y manejadores de error."""
    app = FastAPI(title="ClimApp Lite API", description=DISCLAIMER, version="0.1.0")
    app.add_api_route("/forecast", forecast, methods=["GET"], responses=ERROR_RESPONSES)
    app.add_api_route("/evaluation", evaluation, methods=["GET"], responses=ERROR_RESPONSES)
    app.include_router(reports_router, responses=ERROR_RESPONSES)
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    return app


app = create_app()
