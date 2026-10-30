"""Lectores de las exportaciones de estaciones (csv y xls) con el contador acumulado.

Las dos exportaciones traen las columnas `STATION_ID, SENSORNAME, FECHAYHRA, ED_VALUE`.
En el csv la coma separa campos y también es la coma decimal del valor, por lo que el
valor es todo lo que sigue a la tercera coma (ADR-004).
"""

from collections.abc import Collection, Iterator
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import xlrd

from climapp.data.models import Reading

HEADER = ("STATION_ID", "SENSORNAME", "FECHAYHRA", "ED_VALUE")
TIMESTAMP_FORMAT = "%d/%m/%Y %H:%M"
N_FIELDS = len(HEADER)


def parse_value(raw: str) -> float | None:
    """Convierte un valor con coma decimal en float.

    Args:
        raw: texto del valor, p. ej. `"821,2"`, `"50"` o vacío.

    Returns:
        El número, o `None` si el texto está vacío.

    Raises:
        ValueError: si el texto no es un número con a lo sumo una coma decimal.
    """
    text = raw.strip()
    if not text:
        return None
    if text.count(",") > 1:
        msg = f"valor ambiguo con más de una coma: {text!r}"
        raise ValueError(msg)
    return float(text.replace(",", "."))


def _parse_ts(raw: str, tz: ZoneInfo) -> datetime:
    """Interpreta `dd/mm/aaaa HH:MM` como hora local en `tz`."""
    return datetime.strptime(raw.strip(), TIMESTAMP_FORMAT).replace(tzinfo=tz)


def _csv_reading(line: str, tz: ZoneInfo) -> Reading:
    """Convierte una línea del csv en `Reading` (el valor es el resto tras la 3.ª coma)."""
    station, sensor, ts, value = line.rstrip("\r\n").split(",", N_FIELDS - 1)
    return Reading(station.strip(), sensor.strip(), _parse_ts(ts, tz), parse_value(value))


def read_csv_export(path: Path, sensors: Collection[str], tz: ZoneInfo) -> list[Reading]:
    """Lee la exportación csv y devuelve las lecturas de los sensores pedidos.

    Args:
        path: archivo csv con el encabezado `HEADER`.
        sensors: nombres de sensor que se conservan (contador acumulado).
        tz: zona horaria local de las marcas de tiempo.

    Returns:
        Lecturas en el orden del archivo; los valores vacíos quedan como `None`.

    Raises:
        ValueError: si el encabezado no coincide o una línea está mal formada
            (el mensaje incluye el número de línea).
    """
    with path.open(encoding="ascii") as handle:
        if tuple(handle.readline().strip().split(",")) != HEADER:
            msg = f"encabezado inesperado en {path.name}; se esperaba {','.join(HEADER)}"
            raise ValueError(msg)
        return [
            _csv_line_or_raise(line, number, tz)
            for number, line in enumerate(handle, start=2)
            if line.strip() and line.split(",", 2)[1].strip() in sensors
        ]


def _csv_line_or_raise(line: str, number: int, tz: ZoneInfo) -> Reading:
    """Parsea una línea y relanza el error con su número de línea."""
    try:
        return _csv_reading(line, tz)
    except ValueError as err:
        msg = f"línea {number} mal formada: {err}"
        raise ValueError(msg) from err


def _xls_rows(path: Path) -> Iterator[tuple[int, str, list[xlrd.sheet.Cell]]]:
    """Recorre las filas de todas las hojas, saltando el encabezado y las filas vacías."""
    book = xlrd.open_workbook(str(path), on_demand=True)
    for sheet in book.sheets():
        for index in range(sheet.nrows):
            row = sheet.row(index)
            texts = [str(cell.value).strip() for cell in row[:N_FIELDS]]
            if any(texts) and tuple(texts) != HEADER:
                yield index + 1, sheet.name, row


def _xls_value(cell: xlrd.sheet.Cell) -> float | None:
    """Valor numérico de la celda; el texto se interpreta con coma decimal."""
    if cell.ctype == xlrd.XL_CELL_NUMBER:
        return float(cell.value)
    return parse_value(str(cell.value))


def read_xls_export(path: Path, sensors: Collection[str], tz: ZoneInfo) -> list[Reading]:
    """Lee la exportación xls (varias hojas de ~65 000 filas) con los sensores pedidos.

    Args:
        path: libro xls; solo la primera hoja trae encabezado.
        sensors: nombres de sensor que se conservan.
        tz: zona horaria local de las marcas de tiempo.

    Returns:
        Lecturas en el orden de hojas y filas; celdas vacías como `None`.

    Raises:
        ValueError: si una fila está mal formada (con hoja y fila en el mensaje).
    """
    readings: list[Reading] = []
    for number, sheet, row in _xls_rows(path):
        sensor = str(row[1].value).strip()
        if sensor not in sensors:
            continue
        try:
            ts = _parse_ts(str(row[2].value), tz)
            readings.append(Reading(str(row[0].value).strip(), sensor, ts, _xls_value(row[3])))
        except ValueError as err:
            msg = f"hoja {sheet}, fila {number} mal formada: {err}"
            raise ValueError(msg) from err
    return readings
