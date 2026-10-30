"""Lector de las hojas de cálculo de CHIRPS diario por celda (ADR-004 §2).

Cada libro trae una fila de encabezado (`FECHA` y el número de cada celda), una fila
por día y, al final, un bloque resumen (`ESTADISTICO`, `MIN`, `PROM`, `MAX`) que se
descarta. Las columnas sin número de celda (como la columna resumen extra `GLOBAL`
del archivo 1993-2003) también se descartan.
"""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import openpyxl

DATE_HEADER = "FECHA"
DATE_FORMAT = "%Y.%m.%d"
SUMMARY_LABELS = frozenset({"ESTADISTICO", "MIN", "PROM", "MAX"})


@dataclass(frozen=True, slots=True)
class ChirpsValue:
    """Lluvia diaria de CHIRPS en una celda.

    Attributes:
        day: día UTC de CHIRPS (desfase de 5 h con el día local, ADR-004 §1).
        cell: número de celda del libro (p. ej. 598).
        precip_mm: lluvia del día en mm; `None` si la celda venía vacía.
    """

    day: date
    cell: int
    precip_mm: float | None


def _cell_columns(header: Sequence[object]) -> dict[int, int]:
    """Mapa `índice de columna → celda` para las columnas con número de celda."""
    label = str(header[0] or "").strip().upper() if header else ""
    if label != DATE_HEADER:
        msg = f"encabezado inesperado: la primera columna debe ser {DATE_HEADER}"
        raise ValueError(msg)
    return {i: int(v) for i, v in enumerate(header) if i and isinstance(v, int | float)}


def _parse_day(raw: object) -> date:
    """Día de la primera columna: texto `aaaa.mm.dd` o celda de fecha."""
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    return datetime.strptime(str(raw).strip(), DATE_FORMAT).date()


def _parse_mm(raw: object) -> float | None:
    """Valor numérico de lluvia; vacío como `None`."""
    if raw is None:
        return None
    if isinstance(raw, int | float) and not isinstance(raw, bool):
        return float(raw)
    msg = f"valor de lluvia no numérico: {raw!r}"
    raise ValueError(msg)


def _row_values(row: Sequence[object], columns: dict[int, int]) -> list[ChirpsValue]:
    """Valores de una fila de datos, uno por celda."""
    day = _parse_day(row[0])
    return [ChirpsValue(day, cell, _parse_mm(row[i])) for i, cell in columns.items()]


def _data_rows(path: Path) -> Iterator[tuple[int, tuple[object, ...]]]:
    """Filas de la primera hoja con su número (1 = encabezado)."""
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = book.worksheets[0]
        yield from enumerate(sheet.iter_rows(values_only=True), start=1)
    finally:
        book.close()


def read_chirps_xlsx(path: Path) -> list[ChirpsValue]:
    """Lee un libro de CHIRPS diario y devuelve los valores por día y celda.

    Args:
        path: libro xlsx con la hoja de lluvia diaria como primera hoja.

    Returns:
        Valores en el orden del libro (día, luego celda), sin filas ni columnas resumen.

    Raises:
        ValueError: si falta el encabezado `FECHA`, o una fila tiene una etiqueta o un
            valor no reconocido (el mensaje incluye el número de fila).
    """
    rows = _data_rows(path)
    columns = _cell_columns(next(rows, (1, ()))[1])
    values: list[ChirpsValue] = []
    for number, row in rows:
        label = row[0] if row else None
        if label is None or str(label).strip().upper() in SUMMARY_LABELS:
            continue
        try:
            values.extend(_row_values(row, columns))
        except ValueError as err:
            msg = f"{path.name}, fila {number}: {err}"
            raise ValueError(msg) from err
    return values
