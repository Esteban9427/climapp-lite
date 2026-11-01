"""Nivel del río en la estación de la parte media (TASK-038, ADR-004).

La exportación xlsx trae `STATION_ID, SENSORNAME, FECHAYHRA, ED_VALUE` (nivel en m;
una lectura cada 15 min hasta 2017-03 y cada 10 min desde 2017-04). La serie diaria
guarda, por día local, el nivel mínimo, el máximo y la **subida máxima en 24 h**: para
cada lectura del día, su nivel menos el mínimo de las lecturas de las 24 h anteriores
(incluida ella), y el máximo de eso. Antes se descartan los picos de una sola lectura
(`NIVEL_MAX_STEP_M`, SUPUESTO). Solo se usa como evidencia de crecientes en la
confianza (ADR-002 §4), nunca en el modelo.

Uso: `uv run climapp-level` (lee `.env`; los datos viven en `DATA_DIR`, fuera de git).
"""

import csv
from collections import defaultdict, deque
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import astuple, dataclass, fields
from datetime import date, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from zoneinfo import ZoneInfo

import openpyxl

from climapp.config import Settings
from climapp.data.daily import load_station_map
from climapp.data.models import Reading
from climapp.data.station_reader import HEADER, TIMESTAMP_FORMAT, parse_value
from climapp.logging import configure_logging, get_logger

log = get_logger(__name__)
RISE_WINDOW = timedelta(hours=24)
SPIKE_SPAN = 3  # un pico necesita lectura anterior, la suya y la siguiente


@dataclass(frozen=True, slots=True)
class LevelPoint:
    """Una lectura de nivel: instante con zona horaria y nivel en m."""

    ts: datetime
    level_m: float


@dataclass(frozen=True, slots=True)
class DailyLevel:
    """Resumen diario del nivel de una estación.

    Attributes:
        series_id: identificador público (`EST-x`).
        date: día local.
        n_readings: lecturas con valor en el día.
        level_min_m: nivel mínimo del día.
        level_max_m: nivel máximo del día.
        rise_24h_max_m: subida máxima en 24 h (≥ 0) de las lecturas del día.
    """

    series_id: str
    date: date
    n_readings: int
    level_min_m: float
    level_max_m: float
    rise_24h_max_m: float


def _parse_ts(raw: object, tz: ZoneInfo) -> datetime:
    """Marca de tiempo local: celda de fecha o texto `dd/mm/aaaa HH:MM`."""
    if isinstance(raw, datetime):
        return raw.replace(tzinfo=tz)
    return datetime.strptime(str(raw).strip(), TIMESTAMP_FORMAT).replace(tzinfo=tz)


def _parse_level(raw: object) -> float | None:
    """Nivel numérico, o texto con coma decimal; vacío como `None`."""
    if raw is None:
        return None
    if isinstance(raw, int | float) and not isinstance(raw, bool):
        return float(raw)
    return parse_value(str(raw))


def _rows(path: Path) -> Iterator[tuple[int, tuple[object, ...]]]:
    """Filas de todas las hojas con su número; valida el encabezado de la primera."""
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        for index, sheet in enumerate(book.worksheets):
            rows = enumerate(sheet.iter_rows(values_only=True), start=1)
            if index == 0:
                header = tuple(str(v or "").strip() for v in next(rows, (1, ()))[1][:4])
                if header != HEADER:
                    msg = f"encabezado inesperado en {path.name}; se esperaba {','.join(HEADER)}"
                    raise ValueError(msg)
            yield from rows
    finally:
        book.close()


def read_level_xlsx(path: Path, sensor: str, tz: ZoneInfo) -> list[Reading]:
    """Lee la exportación de nivel y devuelve las lecturas con valor del sensor pedido.

    Args:
        path: libro xlsx con el encabezado `HEADER` en la primera hoja.
        sensor: nombre del sensor de nivel (`LEVEL_SENSOR`).
        tz: zona horaria local de las marcas de tiempo.

    Returns:
        Lecturas en el orden del libro; las celdas vacías se omiten.

    Raises:
        ValueError: si el encabezado no coincide o una fila está mal formada
            (el mensaje incluye el número de fila).
    """
    readings: list[Reading] = []
    for number, row in _rows(path):
        if len(row) < len(HEADER) or str(row[1] or "").strip() != sensor:
            continue
        try:
            value = _parse_level(row[3])
            ts = _parse_ts(row[2], tz)
        except ValueError as err:
            msg = f"{path.name}, fila {number} mal formada: {err}"
            raise ValueError(msg) from err
        if value is not None:
            readings.append(Reading(str(row[0]).strip(), sensor, ts, value))
    return readings


def _unique_sorted(points: Iterable[LevelPoint]) -> list[LevelPoint]:
    """Lecturas en orden de tiempo; ante marcas repetidas se queda la primera."""
    seen: dict[datetime, LevelPoint] = {}
    for point in points:
        seen.setdefault(point.ts, point)
    return sorted(seen.values(), key=lambda p: p.ts)


def _is_spike(up: float, down: float, max_step_m: float) -> bool:
    """`True` si la lectura sube y baja (o baja y sube) más de `max_step_m`."""
    return min(up, down) > max_step_m or max(up, down) < -max_step_m


def drop_single_spikes(points: Iterable[LevelPoint], max_step_m: float) -> list[LevelPoint]:
    """Descarta las lecturas que saltan y regresan en una sola lectura (SUPUESTO).

    Una lectura es un pico si difiere en más de `max_step_m`, en el mismo sentido, de la
    última lectura conservada y de la siguiente (subida y bajada, o bajada y subida). Así,
    una lectura buena entre dos picos no cae. Las lecturas de los extremos se conservan:
    sin vecino a un lado no se ve el regreso. Un pico de dos lecturas no se descarta.

    Args:
        points: lecturas en cualquier orden (las marcas repetidas se descartan).
        max_step_m: salto máximo aceptado (`NIVEL_MAX_STEP_M`).

    Returns:
        Lecturas sin picos, en orden de tiempo.
    """
    ordered = _unique_sorted(points)
    if len(ordered) < SPIKE_SPAN:
        return ordered
    kept = [ordered[0]]
    for point, nxt in pairwise(ordered[1:]):
        up, down = point.level_m - kept[-1].level_m, point.level_m - nxt.level_m
        if not _is_spike(up, down, max_step_m):
            kept.append(point)
    return [*kept, ordered[-1]]


def _rises(points: Sequence[LevelPoint]) -> list[float]:
    """Subida de cada lectura sobre el mínimo de las 24 h anteriores (mínimo deslizante)."""
    window: deque[LevelPoint] = deque()
    rises = []
    for point in points:
        while window and window[0].ts < point.ts - RISE_WINDOW:
            window.popleft()
        while window and window[-1].level_m >= point.level_m:
            window.pop()
        window.append(point)
        rises.append(point.level_m - window[0].level_m)
    return rises


def daily_level(series_id: str, points: Iterable[LevelPoint], tz: ZoneInfo) -> list[DailyLevel]:
    """Serie diaria de nivel de una estación.

    Args:
        series_id: identificador público de la estación.
        points: lecturas en cualquier orden (las marcas repetidas se descartan).
        tz: zona horaria del día local.

    Returns:
        Una fila por día local con lecturas, en orden; los días sin lecturas no aparecen.
    """
    ordered = _unique_sorted(points)
    by_day: dict[date, list[tuple[float, float]]] = defaultdict(list)
    for point, rise in zip(ordered, _rises(ordered), strict=True):
        by_day[point.ts.astimezone(tz).date()].append((point.level_m, rise))
    return [
        DailyLevel(
            series_id=series_id,
            date=day,
            n_readings=len(values),
            level_min_m=min(v for v, _ in values),
            level_max_m=max(v for v, _ in values),
            rise_24h_max_m=max(r for _, r in values),
        )
        for day, values in sorted(by_day.items())
    ]


COLUMNS = [f.name for f in fields(DailyLevel)]


def write_level_csv(rows: Iterable[DailyLevel], path: Path) -> Path:
    """Escribe la serie diaria de nivel como csv (UTF-8) y devuelve la ruta."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        writer.writerows(astuple(row) for row in rows)
    return path


def read_level_csv(path: Path) -> list[DailyLevel]:
    """Lee la serie escrita por `write_level_csv`.

    Raises:
        OSError: si el archivo no se puede leer.
        KeyError, ValueError: si falta una columna o un valor no tiene el tipo esperado.
    """
    with path.open(encoding="utf-8", newline="") as handle:
        return [
            DailyLevel(
                series_id=r["series_id"],
                date=date.fromisoformat(r["date"]),
                n_readings=int(r["n_readings"]),
                level_min_m=float(r["level_min_m"]),
                level_max_m=float(r["level_max_m"]),
                rise_24h_max_m=float(r["rise_24h_max_m"]),
            )
            for r in csv.DictReader(handle)
        ]


def build_level_daily(settings: Settings) -> Path:
    """Regenera `LEVEL_DAILY_FILE` a partir de `LEVEL_EXPORTS` (rutas relativas a `DATA_DIR`).

    Returns:
        Ruta del csv escrito.

    Raises:
        ValueError: si una exportación está mal formada o hay estaciones sin
            correspondencia en `STATION_MAP_FILE`.
        OSError: si un archivo no se puede leer o escribir.
    """
    data_dir, tz = settings.data_dir, settings.local_timezone
    station_map = load_station_map(data_dir / settings.station_map_file)
    points: dict[str, list[LevelPoint]] = defaultdict(list)
    for export in settings.level_exports:
        for r in read_level_xlsx(data_dir / export, settings.level_sensor, tz):
            if r.value is not None:
                points[r.station].append(LevelPoint(r.ts, r.value))
    missing = set(points) - set(station_map)
    if missing:
        msg = f"{len(missing)} estación(es) de nivel sin correspondencia en STATION_MAP_FILE"
        raise ValueError(msg)
    step = settings.nivel_max_step_m
    clean = {raw: drop_single_spikes(pts, step) for raw, pts in points.items()}
    spikes = sum(len(_unique_sorted(pts)) - len(clean[raw]) for raw, pts in points.items())
    rows = [row for raw, pts in clean.items() for row in daily_level(station_map[raw], pts, tz)]
    out = write_level_csv(
        sorted(rows, key=lambda r: (r.series_id, r.date)), data_dir / settings.level_daily_file
    )
    log.info("level.written", path=str(out), rows=len(rows), spikes_dropped=spikes)
    return out


def main() -> None:
    """Punto de entrada de `climapp-level`."""
    configure_logging()
    build_level_daily(Settings())
