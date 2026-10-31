"""Exportación de los incrementos limpios cada 10 min por estación.

Usa exactamente la limpieza de la tabla diaria (`compute_increments`, ADR-004 §2): no hay
otra versión de las reglas. Sirve para revisar eventos lectura a lectura (p. ej. en el
visor de JM). Los periodos de falla conocidos (SP-13) se aplican solo a la tabla diaria.
"""

import csv
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from climapp.data.cleaning import compute_increments
from climapp.data.daily import PRECIP_DECIMALS, DailyConfig, merge_exports
from climapp.data.days import local_day
from climapp.data.models import Increment
from climapp.logging import get_logger

log = get_logger(__name__)
COLUMNS = ("series_id", "fecha_hora_local", "dia_local", "mm", "flag")


@dataclass(frozen=True, slots=True)
class StationIncrement:
    """Incremento limpio de una estación, con su identificador público."""

    series_id: str
    increment: Increment


def build_station_increments(
    exports: Sequence[Path], station_map: Mapping[str, str], config: DailyConfig
) -> list[StationIncrement]:
    """Incrementos limpios de todas las estaciones, ordenados por serie e instante.

    Raises:
        ValueError: si una exportación tiene formato desconocido o hay estaciones sin
            correspondencia en el mapa.
    """
    merged = merge_exports(exports, station_map, config)
    rows = [
        StationIncrement(station_map[raw], inc)
        for raw, pairs in merged.readings_by_station.items()
        for inc in compute_increments([reading for reading, _ in pairs], config.cleaning)
    ]
    return sorted(rows, key=lambda r: (r.series_id, r.increment.ts))


def write_increments_csv(rows: Iterable[StationIncrement], path: Path) -> Path:
    """Escribe los incrementos (UTF-8) con hora y día locales; devuelve la ruta.

    El día local sigue la convención de la tabla diaria: la lectura de las 00:00 cierra
    el día anterior.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for row in rows:
            inc = row.increment
            writer.writerow(
                (
                    row.series_id,
                    inc.ts.strftime("%Y-%m-%d %H:%M"),
                    local_day(inc.ts).isoformat(),
                    round(inc.mm, PRECIP_DECIMALS),
                    inc.flag.value,
                )
            )
            count += 1
    log.info("increments.written", path=str(path), rows=count)
    return path
