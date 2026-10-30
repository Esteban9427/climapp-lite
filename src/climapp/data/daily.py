"""Tabla diaria de estaciones a partir de las exportaciones del contador (ADR-004).

Una lectura cierra el paso de 10 min que termina en su instante, así que la lectura de
las 00:00 pertenece al día local anterior. El día es válido con al menos
`min_readings` lecturas con valor (SUPUESTO, SP-8); si no, `precip_mm` queda vacío.
Las exportaciones se unen por `(estación, instante)`: ante repetidos gana la primera.
"""

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from climapp.config import Settings
from climapp.data.cleaning import CleaningParams, compute_increments
from climapp.data.days import local_day
from climapp.data.models import GAP_FLAGS, DailyPrecip, Increment, Reading, StepFlag
from climapp.data.station_reader import read_csv_export, read_xls_export
from climapp.logging import get_logger

log = get_logger(__name__)

PUBLIC_ID = re.compile(r"^EST-[A-Z]$")
PRECIP_DECIMALS = 3  # el pluviómetro mide en décimas: 3 decimales solo quitan ruido flotante
HASH_CHUNK_BYTES = 1 << 20
READERS = {".csv": read_csv_export, ".xls": read_xls_export}


@dataclass(frozen=True, slots=True)
class DailyConfig:
    """Parámetros de la tabla diaria de estaciones.

    Attributes:
        sensors: sensores del contador acumulado (`COUNTER_SENSORS`).
        tz: zona horaria local (`LOCAL_TIMEZONE`).
        cleaning: umbrales de limpieza del contador.
        min_readings: lecturas mínimas por día válido (`MIN_READINGS`, SUPUESTO).
    """

    sensors: Collection[str]
    tz: ZoneInfo
    cleaning: CleaningParams
    min_readings: int

    @classmethod
    def from_settings(cls, settings: Settings) -> "DailyConfig":
        """Construye la configuración a partir de `Settings`."""
        cleaning = CleaningParams(
            max_step_mm=settings.max_step_mm,
            suspect_step_mm=settings.suspect_step_mm,
            suspect_quiet=timedelta(minutes=settings.suspect_quiet_min),
            suspect_quiet_max_mm=settings.suspect_quiet_max_mm,
            max_gap=timedelta(minutes=settings.max_gap_min),
        )
        return cls(
            settings.counter_sensors, settings.local_timezone, cleaning, settings.min_readings
        )


@dataclass(frozen=True, slots=True)
class SourcedReadings:
    """Lecturas de una exportación junto con el SHA-256 del archivo crudo."""

    source_hash: str
    readings: Sequence[Reading]


@dataclass(slots=True)
class MergedReadings:
    """Unión de exportaciones: por estación cruda, lecturas `(lectura, hash)` sin repetir.

    Attributes:
        readings_by_station: lecturas por nombre crudo de estación, en orden de llegada.
        conflicts: instantes repetidos con valores distintos (se conservó el primero).
    """

    readings_by_station: dict[str, list[tuple[Reading, str]]] = field(default_factory=dict)
    conflicts: int = 0


def merge_sources(sources: Iterable[SourcedReadings]) -> MergedReadings:
    """Une exportaciones sin duplicar lecturas de la misma estación e instante.

    Args:
        sources: exportaciones en orden de preferencia.

    Returns:
        La unión, con el número de conflictos (mismo instante, valor distinto).
    """
    merged = MergedReadings()
    seen: dict[tuple[str, datetime], float | None] = {}
    for source in sources:
        for reading in source.readings:
            key = (reading.station, reading.ts)
            if key in seen:
                merged.conflicts += seen[key] != reading.value
                continue
            seen[key] = reading.value
            pairs = merged.readings_by_station.setdefault(reading.station, [])
            pairs.append((reading, source.source_hash))
    return merged


@dataclass(slots=True)
class _DayTally:
    """Acumuladores de un día local."""

    n_readings: int = 0
    hashes: set[str] = field(default_factory=set)
    mm: float = 0.0
    n_suspect: int = 0
    n_gap: int = 0


def _tally(
    pairs: Sequence[tuple[Reading, str]], incs: Sequence[Increment]
) -> dict[date, _DayTally]:
    """Cuenta lecturas, hashes, lluvia, saltos `suspect` y huecos por día local."""
    days: defaultdict[date, _DayTally] = defaultdict(_DayTally)
    for reading, digest in pairs:
        if reading.value is not None:
            day = days[local_day(reading.ts)]
            day.n_readings += 1
            day.hashes.add(digest)
    for inc in incs:
        day = days[local_day(inc.ts)]
        day.mm += inc.mm
        day.n_suspect += inc.flag is StepFlag.SUSPECT
        day.n_gap += inc.flag in GAP_FLAGS
    return days


def _row(series_id: str, day: date, tally: _DayTally, min_readings: int) -> DailyPrecip:
    """Fila diaria a partir de los acumuladores del día."""
    valid = tally.n_readings >= min_readings
    return DailyPrecip(
        date=day,
        series_id=series_id,
        precip_mm=round(tally.mm, PRECIP_DECIMALS) if valid else None,
        n_readings=tally.n_readings,
        valid=valid,
        imputed=False,
        source_hash=",".join(sorted(tally.hashes)),
        n_suspect=tally.n_suspect,
        n_gap=tally.n_gap,
    )


def daily_for_station(
    series_id: str,
    pairs: Sequence[tuple[Reading, str]],
    params: CleaningParams,
    min_readings: int,
) -> list[DailyPrecip]:
    """Tabla diaria de una estación, con todos los días entre la primera y la última lectura.

    Args:
        series_id: identificador público (`EST-A`…).
        pairs: lecturas `(lectura, hash del archivo)` de una sola estación cruda.
        params: umbrales de limpieza del contador.
        min_readings: lecturas mínimas para que el día sea válido (`MIN_READINGS`).

    Returns:
        Una fila por día local, en orden; los días sin lecturas quedan inválidos.
    """
    incs = compute_increments([reading for reading, _ in pairs], params)
    days = _tally(pairs, incs)
    counted = [d for d, t in days.items() if t.n_readings]
    if not counted:
        return []
    first, last = min(counted), max(counted)
    span = (first + timedelta(days=i) for i in range((last - first).days + 1))
    return [_row(series_id, d, days.get(d, _DayTally()), min_readings) for d in span]


def load_station_map(path: Path) -> dict[str, str]:
    """Lee la correspondencia `nombre crudo → EST-x`, que vive fuera de git (D-03).

    Raises:
        ValueError: si algún destino no es un identificador público `EST-<letra>`.
    """
    mapping: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
    if not all(PUBLIC_ID.match(v) for v in mapping.values()):
        msg = "STATION_MAP_FILE solo puede mapear a identificadores EST-A…EST-Z"
        raise ValueError(msg)
    return mapping


def file_sha256(path: Path) -> str:
    """SHA-256 hexadecimal del archivo, leído por bloques."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _read_export(path: Path, sensors: Collection[str], tz: ZoneInfo) -> SourcedReadings:
    """Lee una exportación según su extensión y la etiqueta con su hash."""
    reader = READERS.get(path.suffix.lower())
    if reader is None:
        msg = f"formato de exportación no soportado: {path.suffix} ({path.name})"
        raise ValueError(msg)
    return SourcedReadings(file_sha256(path), reader(path, sensors, tz))


def build_station_daily(
    exports: Sequence[Path], station_map: Mapping[str, str], config: DailyConfig
) -> list[DailyPrecip]:
    """Construye la tabla diaria de todas las estaciones uniendo las exportaciones.

    Args:
        exports: exportaciones en orden de preferencia (csv o xls).
        station_map: correspondencia nombre crudo → `EST-x`.
        config: sensores, zona horaria, limpieza y mínimo de lecturas.

    Returns:
        Filas ordenadas por serie y fecha.

    Raises:
        ValueError: si una exportación tiene formato desconocido o hay estaciones sin
            correspondencia en el mapa.
    """
    merged = merge_sources(_read_export(p, config.sensors, config.tz) for p in exports)
    missing = set(merged.readings_by_station) - set(station_map)
    if missing:
        msg = f"{len(missing)} estación(es) sin correspondencia en STATION_MAP_FILE"
        raise ValueError(msg)
    log.info("daily.merged", exports=len(exports), conflicts=merged.conflicts)
    rows = [
        row
        for raw, pairs in merged.readings_by_station.items()
        for row in daily_for_station(station_map[raw], pairs, config.cleaning, config.min_readings)
    ]
    return sorted(rows, key=lambda r: (r.series_id, r.date))


def _csv_cell(value: object) -> str:
    """Texto de una celda: booleanos en minúscula y `None` como vacío."""
    if isinstance(value, bool):
        return str(value).lower()
    return "" if value is None else str(value)


def write_daily_csv(rows: Iterable[DailyPrecip], path: Path) -> Path:
    """Escribe la tabla diaria como csv (UTF-8) y devuelve la ruta.

    Args:
        rows: filas de la tabla.
        path: destino; se crean los directorios que falten.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = list(DailyPrecip.model_fields)
    counts: Counter[str] = Counter()
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(_csv_cell(getattr(row, c)) for c in columns)
            counts[row.series_id] += 1
    log.info("daily.written", path=str(path), rows=dict(counts))
    return path
