"""API de ClimApp Lite (`docs/openapi.yaml`). No es una alerta oficial.

Uso: `uv run uvicorn climapp.api.main:app`.
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from climapp.api.deps import ApiError, get_now, get_settings
from climapp.api.forecast_routes import (
    DISCLAIMER,
    disclaimer_text,
    evaluation,
    forecast,
    get_explainer,
)
from climapp.api.reports import router as reports_router
from climapp.api.schemas import Error
from climapp.logging import get_logger
from climapp.web.views import router as web_router

log = get_logger(__name__)
__all__ = [
    "DISCLAIMER",
    "ApiError",
    "create_app",
    "disclaimer_text",
    "get_explainer",
    "get_now",
    "get_settings",
]
STATIC_DIR = Path(__file__).resolve().parents[1] / "web" / "static"
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    422: {"model": Error},
    503: {"model": Error},
}


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
    app.include_router(web_router, include_in_schema=False)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    return app


app = create_app()
