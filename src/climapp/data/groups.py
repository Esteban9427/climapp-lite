"""Grupos de estaciones correlacionadas que cuentan como una sola fuente (ADR-002 §4).

Versión mínima de TASK-002 (lo que necesita TASK-014): r de Pearson diario por pares
sobre **toda** la tabla diaria (de `TRAIN_START` a `TEST_END`), con los días válidos y no
imputados. EST-C y EST-D empiezan en 2023, después de `VALID_END`: con solo el
entrenamiento no se podría medir ningún grupo (decisión del equipo, 2026-10-31). Los
grupos solo afectan la confianza de los reportes, no la evaluación del pronóstico.
Las estaciones con r >= `min_r` se agrupan como componentes conexas (si A~B y B~C, las
tres son un grupo): agrupar de más solo baja la confianza, nunca la infla.
"""

import json
import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from itertools import combinations
from pathlib import Path

import numpy as np

from climapp.config import Settings
from climapp.data.daily import PUBLIC_ID, read_daily_csv
from climapp.data.models import DailyPrecip
from climapp.logging import configure_logging, get_logger

log = get_logger(__name__)
MIN_POINTS = 2  # r de Pearson necesita al menos dos días comunes


@dataclass(frozen=True, slots=True)
class GroupingParams:
    """Parámetros del agrupamiento.

    Attributes:
        start: primer día del periodo (`TRAIN_START`).
        end: último día del periodo (`TEST_END`).
        min_r: r mínimo para agrupar (`STATION_GROUP_MIN_R`, 0,8, SUPUESTO).
        min_overlap_days: días comunes mínimos para estimar r
            (`STATION_GROUP_MIN_OVERLAP_DAYS`, SUPUESTO).
    """

    start: date
    end: date
    min_r: float
    min_overlap_days: int


@dataclass(frozen=True, slots=True)
class StationPair:
    """Correlación diaria de dos estaciones (`a` < `b`) en sus días comunes."""

    a: str
    b: str
    r: float
    n_days: int


def _station_values(
    rows: Iterable[DailyPrecip], params: GroupingParams
) -> dict[str, dict[date, float]]:
    """Lluvia por estación y día, solo días válidos, no imputados y dentro del periodo."""
    values: defaultdict[str, dict[date, float]] = defaultdict(dict)
    for row in rows:
        mm = row.precip_mm
        in_period = params.start <= row.date <= params.end
        if mm is None or not row.valid or row.imputed or not in_period:
            continue
        if PUBLIC_ID.match(row.series_id):
            values[row.series_id][row.date] = mm
    return dict(values)


def _pearson(x: Mapping[date, float], y: Mapping[date, float]) -> tuple[float, int]:
    """r de Pearson en los días comunes y su número; `nan` si una serie es constante."""
    days = sorted(x.keys() & y.keys())
    a = np.array([x[d] for d in days])
    b = np.array([y[d] for d in days])
    if len(days) < MIN_POINTS or a.std() == 0 or b.std() == 0:
        return math.nan, len(days)
    return float(np.corrcoef(a, b)[0, 1]), len(days)


def pairwise_correlations(rows: Iterable[DailyPrecip], params: GroupingParams) -> list[StationPair]:
    """Correlación de cada par de estaciones con suficientes días comunes.

    Args:
        rows: tabla diaria (las series que no son `EST-x` se ignoran).
        params: periodo, r mínimo y días comunes mínimos.

    Returns:
        Pares ordenados por nombre; se omiten los de pocos días o r indefinido.
    """
    values = _station_values(rows, params)
    pairs = []
    for a, b in combinations(sorted(values), 2):
        r, n = _pearson(values[a], values[b])
        if n >= params.min_overlap_days and not math.isnan(r):
            pairs.append(StationPair(a=a, b=b, r=r, n_days=n))
    return pairs


def _components(nodes: Sequence[str], edges: Iterable[tuple[str, str]]) -> list[tuple[str, ...]]:
    """Componentes conexas del grafo, cada una ordenada y en orden de su primer miembro."""
    parent = {n: n for n in nodes}

    def root(n: str) -> str:
        while parent[n] != n:
            n = parent[n]
        return n

    for a, b in edges:
        parent[root(b)] = root(a)
    groups: defaultdict[str, list[str]] = defaultdict(list)
    for n in nodes:
        groups[root(n)].append(n)
    return sorted(tuple(sorted(g)) for g in groups.values())


def station_groups(rows: Iterable[DailyPrecip], params: GroupingParams) -> list[tuple[str, ...]]:
    """Grupos de estaciones con r >= `min_r`; una estación sin pareja es su propio grupo.

    Args:
        rows: tabla diaria.
        params: periodo, r mínimo y días comunes mínimos.

    Returns:
        Grupos ordenados; cada estación con algún día válido en el periodo aparece una vez.
    """
    rows = list(rows)
    nodes = sorted(_station_values(rows, params))
    edges = [(p.a, p.b) for p in pairwise_correlations(rows, params) if p.r >= params.min_r]
    return _components(nodes, edges)


def build_groups(settings: Settings) -> Path:
    """Calcula los grupos sobre `DAILY_STATIONS_FILE` y escribe `STATION_GROUPS_FILE`.

    Raises:
        OSError: si la tabla diaria no se puede leer o el artefacto no se puede escribir.
        pydantic.ValidationError: si la tabla diaria no es válida.
    """
    params = GroupingParams(
        start=settings.train_start,
        end=settings.test_end,
        min_r=settings.station_group_min_r,
        min_overlap_days=settings.station_group_min_overlap_days,
    )
    rows = read_daily_csv(settings.data_dir / settings.daily_stations_file)
    payload = {
        "min_r": params.min_r,
        "period": {"start": params.start.isoformat(), "end": params.end.isoformat()},
        "pairs": [asdict(p) for p in pairwise_correlations(rows, params)],
        "groups": [list(g) for g in station_groups(rows, params)],
    }
    out = settings.data_dir / settings.station_groups_file
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    log.info("groups.written", path=str(out), groups=payload["groups"])
    return out


def main() -> None:
    """Punto de entrada de `climapp-groups`."""
    configure_logging()
    build_groups(Settings())
