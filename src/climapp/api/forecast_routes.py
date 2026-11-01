"""Rutas `GET /forecast` y `GET /evaluation`, y el aviso de canales oficiales.

Las usan la API (`main.py`) y las vistas web (`climapp.web.views`).
"""

from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Query

from climapp.api.artifacts import (
    ArtifactInvalidError,
    ArtifactMissingError,
    find_forecast,
    load_evaluation,
)
from climapp.api.deps import ApiError, NowDep, SettingsDep
from climapp.api.schemas import Forecast
from climapp.config import Settings, TargetRule
from climapp.forecast.context import load_context, risk_level
from climapp.forecast.evaluation import EvaluationReport
from climapp.forecast.features import Variant
from climapp.forecast.publish import ForecastRecord
from climapp.verification.explain import Explainer, build_explainer

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


def _decision_threshold(settings: Settings, variant: Variant) -> float | None:
    """Umbral de aviso del RF calibrado de la variante, fijado fuera de la prueba."""
    try:
        report = load_evaluation(settings.data_dir / settings.evaluation_file)
    except (ArtifactMissingError, ArtifactInvalidError):
        return None
    found = [
        m.threshold
        for m in report.scenarios.con_est_b
        if m.name == "rf" and m.variant == variant and m.calibrated
    ]
    return found[0] if found else None


def _with_context(forecast: Forecast, settings: Settings) -> Forecast:
    """Percentil del acumulado, climatología del día, umbral de aviso y riesgo (ADR-001 §11)."""
    context = load_context(settings)
    threshold = _decision_threshold(settings, forecast.variant)
    update = {
        "accum_3d_percentile": context.accum3_percentile(forecast.accum_3d_mm) if context else None,
        "climatology_prob": context.climatology(forecast.target_date) if context else None,
        "decision_threshold": threshold,
        "risk": risk_level(forecast.prob_ge_threshold, threshold),
    }
    return forecast.model_copy(update=update)


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
        variant: variante pedida; por defecto `operativa`, también en la reproducción.

    Returns:
        El pronóstico con el aviso y el enlace oficial.

    Raises:
        ApiError: 422 si se pide `historica` sin `replay_date`; 503 sin pronóstico.
    """
    chosen: Variant = variant or "operativa"  # también en la reproducción (2026-11-01)
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
    built = _with_context(
        _to_forecast(record, settings, now, replay=replay_date is not None), settings
    )
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
