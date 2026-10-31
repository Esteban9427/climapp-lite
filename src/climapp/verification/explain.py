"""Explicación del pronóstico con Muse Spark, verificada por la compuerta (TASK-022).

Las cifras se le entregan al modelo ya redondeadas como las compara la compuerta
(probabilidad en % entero, milímetros con 1 decimal; ADR-002 §3) y el texto solo puede
citarlas a ellas. Si la explicación no pasa la compuerta, o Muse no responde, el
pronóstico sale con `explanation=null`.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import ValidationError

from climapp.api.schemas import Forecast
from climapp.config import Settings
from climapp.logging import get_logger
from climapp.verification.gate import GateRequest, run_gate
from climapp.verification.muse import MuseClient, MuseError, MuseTask, build_client
from climapp.verification.prompts import explain_messages
from climapp.verification.schemas import ForecastExplanation

log = get_logger(__name__)
PERCENT = 100
MM_DECIMALS = 1


@dataclass(frozen=True, slots=True)
class VerifiedExplanation:
    """Texto que pasó la compuerta y si viene de respuestas grabadas."""

    text: str
    fallback: bool


Explainer = Callable[[Forecast], VerifiedExplanation | None]


def forecast_figures(forecast: Forecast) -> dict[str, float]:
    """Cifras que la explicación puede citar, redondeadas como se comparan."""
    figures: dict[str, float] = {
        "probabilidad_pct": round(forecast.prob_ge_threshold * PERCENT),
        "umbral_mm": forecast.threshold_mm,
    }
    if forecast.accum_3d_mm is not None:
        figures["acumulado_3d_mm"] = round(forecast.accum_3d_mm, MM_DECIMALS)
    return figures


def _request(forecast: Forecast) -> GateRequest[ForecastExplanation]:
    """Pedido de la compuerta: cifras, contexto y la misma información para el juez."""
    figures = forecast_figures(forecast)
    context: dict[str, float | str] = {
        **figures,
        "nivel_acumulado_3d": forecast.accum_3d_level,
        "aviso": forecast.disclaimer,
    }
    return GateRequest(
        task=MuseTask.EXPLAIN,
        schema=ForecastExplanation,
        messages=explain_messages(context),
        allowed_numbers=frozenset(figures.values()),
        evidence=json.dumps({"datos_del_pronostico": context}, ensure_ascii=False),
    )


def explain_forecast(
    client: MuseClient, forecast: Forecast, max_attempts: int
) -> VerifiedExplanation | None:
    """Explicación verificada del pronóstico, o `None` si no pasa la compuerta.

    Args:
        client: cliente Muse (real o grabado).
        forecast: pronóstico a explicar.
        max_attempts: intentos de la compuerta (`VERIFY_MAX_ATTEMPTS`).
    """
    try:
        result = run_gate(client, _request(forecast), max_attempts)
    except MuseError as err:
        log.warning("explain.muse_error", error=str(err))
        return None
    log.info("explain.done", status=result.status, attempts=len(result.attempts))
    if result.output is None:
        return None
    return VerifiedExplanation(text=result.output.text, fallback=result.fallback)


class _CachedExplainer:
    """Explica cada emisión una sola vez y crea el cliente Muse al primer uso."""

    def __init__(self, settings: Settings) -> None:
        """Guarda la configuración; el cliente se crea cuando hace falta."""
        self._settings = settings
        self._client: MuseClient | None = None
        self._cache: dict[tuple[object, ...], VerifiedExplanation | None] = {}

    def __call__(self, forecast: Forecast) -> VerifiedExplanation | None:
        """Explicación de la emisión, desde la memoria si ya se pidió."""
        key = (forecast.target_date, forecast.variant, forecast.model_version, forecast.replay)
        if key not in self._cache:
            self._cache[key] = self._explain(forecast)
        return self._cache[key]

    def _explain(self, forecast: Forecast) -> VerifiedExplanation | None:
        """Crea el cliente si falta y pide la explicación."""
        try:
            self._client = self._client or build_client(self._settings)
        except (OSError, ValidationError) as err:
            log.warning("explain.client_error", error=type(err).__name__)
            return None
        return explain_forecast(self._client, forecast, self._settings.verify_max_attempts)


def build_explainer(settings: Settings) -> Explainer | None:
    """Explicador según la configuración; `None` sin `META_API_KEY` ni `DEMO_FALLBACK`."""
    if not settings.demo_fallback and not settings.meta_api_key.get_secret_value():
        return None
    return _CachedExplainer(settings)
