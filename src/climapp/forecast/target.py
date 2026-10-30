"""Objetivo "≥ umbral en la cuenca" sobre la tabla diaria de estaciones (ADR-001 §2).

Regla principal `basin_mean` (SUPUESTO, PRD SP-6): media de las estaciones válidas del
día. Los valores imputados nunca entran al objetivo (ADR-004 §3). Las reglas
`any_station` y `reference_station` son la sensibilidad Should de TASK-032.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from statistics import fmean, pstdev

from climapp.config import TargetRule
from climapp.data.models import DailyPrecip

STATION_PREFIX = "EST-"


@dataclass(frozen=True, slots=True)
class BasinDay:
    """Agregados de la cuenca en un día, con las estaciones válidas disponibles.

    Attributes:
        date: día local.
        n_stations: estaciones válidas y no imputadas que entran.
        mean_mm: media de esas estaciones; `None` si no hay ninguna.
        max_mm: máximo; `None` si no hay ninguna.
        std_mm: desviación estándar poblacional; `None` si no hay ninguna.
    """

    date: date
    n_stations: int
    mean_mm: float | None
    max_mm: float | None
    std_mm: float | None


def _aggregate(day: date, values: list[float]) -> BasinDay:
    """Agregados de un día a partir de los valores válidos de las estaciones."""
    if not values:
        return BasinDay(day, 0, None, None, None)
    return BasinDay(day, len(values), fmean(values), max(values), pstdev(values))


def basin_days(rows: Iterable[DailyPrecip]) -> dict[date, BasinDay]:
    """Agrega por día las estaciones válidas y no imputadas.

    Args:
        rows: filas de la tabla diaria; las series que no son `EST-*` se ignoran.

    Returns:
        Agregados por día, para cada día que tenga al menos una fila de estación.
    """
    values: defaultdict[date, list[float]] = defaultdict(list)
    for row in rows:
        if not row.series_id.startswith(STATION_PREFIX):
            continue
        day_values = values[row.date]
        if row.valid and not row.imputed and row.precip_mm is not None:
            day_values.append(row.precip_mm)
    return {day: _aggregate(day, vals) for day, vals in sorted(values.items())}


def observed_event(day: BasinDay, rule: TargetRule, threshold_mm: float) -> bool | None:
    """Indica si el día alcanzó el umbral en la cuenca según la regla.

    Args:
        day: agregados del día.
        rule: regla del objetivo (`TARGET_RULE`).
        threshold_mm: umbral diario (`FORECAST_THRESHOLD_MM`, 20 mm).

    Returns:
        `True` o `False`; `None` si no hay estaciones válidas.

    Raises:
        ValueError: si la regla todavía no está implementada.
    """
    if rule != "basin_mean":
        msg = f"regla {rule} no implementada: es la sensibilidad Should de TASK-032"
        raise ValueError(msg)
    return None if day.mean_mm is None else day.mean_mm >= threshold_mm
