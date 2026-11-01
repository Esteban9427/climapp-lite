"""Contexto del pronóstico calculado por código, sin tocar el modelo (ADR-001 §11).

- Percentil del acumulado de 3 días frente a la serie de entrenamiento (emisiones entre
  `TRAIN_START` y `VALID_END`), con la misma definición que la variable `accum3_mean`:
  suma de la media de la cuenca del día de emisión y de los dos anteriores.
- Climatología del día objetivo: frecuencia del evento en el entrenamiento, ±
  `CLIMATOLOGY_WINDOW_DAYS` alrededor del día del año (la misma línea base de ADR-001).
- Riesgo: la probabilidad frente al umbral de aviso de la variante, que se fijó fuera de
  la prueba (`decision_threshold`).
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from climapp.config import Settings, TargetRule
from climapp.data.daily import read_daily_csv
from climapp.forecast.baselines import climatology_probs
from climapp.forecast.features import LAGS
from climapp.forecast.target import BasinDay, basin_days, observed_event
from climapp.logging import get_logger

log = get_logger(__name__)
PERCENT = 100
Risk = Literal["elevado", "habitual"]


@dataclass(frozen=True, slots=True)
class ForecastContext:
    """Serie de entrenamiento para el contexto del pronóstico.

    Attributes:
        accum3_train: acumulados de 3 días de las emisiones del entrenamiento, ordenados.
        observed_train: evento observado por día del entrenamiento (`None` sin dato).
        window_days: semiancho de la ventana de la climatología.
    """

    accum3_train: tuple[float, ...]
    observed_train: Mapping[date, bool | None]
    window_days: int

    def accum3_percentile(self, value: float | None) -> int | None:
        """% de días del entrenamiento con un acumulado menor que `value` (entero hacia abajo)."""
        if value is None or not self.accum3_train:
            return None
        below = sum(1 for v in self.accum3_train if v < value)
        return math.floor(PERCENT * below / len(self.accum3_train))

    def climatology(self, target: date) -> float | None:
        """Frecuencia del evento cerca del día del año de `target`; `None` sin días cerca."""
        try:
            return climatology_probs(self.observed_train, [target], self.window_days)[0]
        except ValueError:
            return None


def _accum3(issue: date, basin: Mapping[date, BasinDay]) -> float | None:
    """Suma de la media de la cuenca en los días de `LAGS`; `None` si falta alguno."""
    days = (issue - timedelta(days=lag) for lag in LAGS)
    means = [basin[d].mean_mm if d in basin else None for d in days]
    return None if any(m is None for m in means) else sum(m for m in means if m is not None)


def build_context(  # noqa: PLR0913 - parámetros explícitos del periodo y del objetivo
    basin: Mapping[date, BasinDay],
    *,
    start: date,
    end: date,
    threshold_mm: float,
    rule: TargetRule,
    window_days: int,
) -> ForecastContext:
    """Arma el contexto con los días de `basin` entre `start` y `end` (incluidos)."""
    train = [d for d in basin if start <= d <= end]
    accums = (_accum3(d, basin) for d in train)
    observed = {d: observed_event(basin[d], rule, threshold_mm) for d in train}
    return ForecastContext(tuple(sorted(a for a in accums if a is not None)), observed, window_days)


def risk_level(prob: float, threshold: float | None) -> Risk | None:
    """ "elevado" si `prob` llega al umbral de aviso de la variante; `None` sin umbral."""
    if threshold is None:
        return None
    return "elevado" if prob >= threshold else "habitual"


@lru_cache(maxsize=4)
def _cached(
    path: Path, mtime_ns: int, params: tuple[date, date, float, TargetRule, int]
) -> ForecastContext:
    """Contexto de la tabla diaria, una vez por versión del archivo y de los parámetros."""
    del mtime_ns  # solo forma parte de la clave de la caché
    start, end, threshold_mm, rule, window_days = params
    basin = basin_days(read_daily_csv(path))
    return build_context(
        basin, start=start, end=end, threshold_mm=threshold_mm, rule=rule, window_days=window_days
    )


def load_context(settings: Settings) -> ForecastContext | None:
    """Contexto desde `DAILY_STATIONS_FILE`; `None` si la tabla falta o no es válida."""
    path = settings.data_dir / settings.daily_stations_file
    try:
        params = (
            settings.train_start,
            settings.valid_end,
            settings.forecast_threshold_mm,
            settings.target_rule,
            settings.climatology_window_days,
        )
        return _cached(path, path.stat().st_mtime_ns, params)
    except (OSError, ValidationError, ValueError) as err:
        log.warning("context.unavailable", error=type(err).__name__)
        return None
