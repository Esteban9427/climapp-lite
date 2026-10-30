"""Variables del modelo para una fecha de emisión `t` que pronostica `t + 1` (ADR-001 §3).

Agregados de la cuenca en t, t-1 y t-2 con las estaciones disponibles cada día, número
de estaciones, acumulado de 3 días, CHIRPS (media de las celdas, día UTC) en t y t-1 y
estacionalidad del día objetivo. Solo se usan datos hasta `t`: los faltantes son NaN.
"""

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta

from climapp.data.chirps_reader import ChirpsValue
from climapp.forecast.target import BasinDay

LAGS = (0, 1, 2)
DAYS_PER_YEAR = 365.25
NAN = math.nan
FEATURE_NAMES: tuple[str, ...] = (
    *(f"{stat}_t{lag}" for lag in LAGS for stat in ("mean", "max", "std")),
    "n_stations_t0",
    "accum3_mean",
    "chirps_t0",
    "chirps_t1",
    "doy_sin",
    "doy_cos",
)


@dataclass(frozen=True, slots=True)
class FeatureRow:
    """Variables de una fecha de emisión, en el orden de `FEATURE_NAMES`."""

    issue_date: date
    target_date: date
    values: tuple[float, ...]


def chirps_daily_mean(values: Iterable[ChirpsValue]) -> dict[date, float]:
    """Media diaria de las celdas de CHIRPS con valor."""
    cells: defaultdict[date, list[float]] = defaultdict(list)
    for value in values:
        if value.precip_mm is not None:
            cells[value.day].append(value.precip_mm)
    return {day: sum(mm) / len(mm) for day, mm in sorted(cells.items())}


def _or_nan(value: float | None) -> float:
    """`None` como NaN, que el random forest acepta como faltante."""
    return NAN if value is None else value


def _basin_stats(day: BasinDay | None) -> tuple[float, float, float]:
    """Media, máximo y dispersión del día; NaN si no hay estaciones."""
    if day is None:
        return NAN, NAN, NAN
    return _or_nan(day.mean_mm), _or_nan(day.max_mm), _or_nan(day.std_mm)


def _seasonality(target: date) -> tuple[float, float]:
    """Seno y coseno del día del año objetivo."""
    angle = 2 * math.pi * target.timetuple().tm_yday / DAYS_PER_YEAR
    return math.sin(angle), math.cos(angle)


def feature_row(
    issue: date, basin: Mapping[date, BasinDay], chirps: Mapping[date, float]
) -> FeatureRow:
    """Construye las variables para la emisión del día `issue`.

    Args:
        issue: fecha de emisión (último día con datos que puede usar el modelo).
        basin: agregados de la cuenca por día.
        chirps: media diaria de CHIRPS por día.

    Returns:
        La fila de variables; los datos faltantes quedan como NaN.
    """
    days = [issue - timedelta(days=lag) for lag in LAGS]
    stats = [_basin_stats(basin.get(day)) for day in days]
    today = basin.get(issue)
    means = [s[0] for s in stats]
    values = (
        *(v for s in stats for v in s),
        float(today.n_stations if today else 0),
        sum(means) if not any(math.isnan(m) for m in means) else NAN,
        chirps.get(issue, NAN),
        chirps.get(issue - timedelta(days=1), NAN),
        *_seasonality(issue + timedelta(days=1)),
    )
    return FeatureRow(issue, issue + timedelta(days=1), values)
