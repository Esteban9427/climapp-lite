"""Tests del lector de las exportaciones de estaciones (TASK-003). Datos sintéticos."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import xlwt

from climapp.data.station_reader import parse_value, read_csv_export, read_xls_export

TZ = ZoneInfo("America/Bogota")
SENSORS = ("P", "PRECIP")
CSV_HEADER = "STATION_ID,SENSORNAME,FECHAYHRA,ED_VALUE"


def _csv(tmp_path: Path, *lines: str) -> Path:
    path = tmp_path / "export.csv"
    path.write_text("\n".join((CSV_HEADER, *lines)) + "\n", encoding="ascii")
    return path


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("821,20000000000005", 821.2), ("50", 50.0), ("0,2", 0.2), ("", None), ("  ", None)],
)
def test_parse_value_handles_decimal_comma_and_empty(raw: str, expected: float | None) -> None:
    assert parse_value(raw) == pytest.approx(expected)


def test_parse_value_rejects_ambiguous_text() -> None:
    with pytest.raises(ValueError, match="1,2,3"):
        parse_value("1,2,3")


def test_csv_reads_counter_with_decimal_comma_and_local_time(tmp_path: Path) -> None:
    path = _csv(tmp_path, "EST-A,P,16/08/2013 11:50,821,20000000000005")
    (reading,) = read_csv_export(path, SENSORS, TZ)
    assert reading.station == "EST-A"
    assert reading.sensor == "P"
    assert reading.ts == datetime(2013, 8, 16, 11, 50, tzinfo=TZ)
    assert reading.value == pytest.approx(821.2)


def test_csv_keeps_empty_values_as_none_and_filters_sensors(tmp_path: Path) -> None:
    path = _csv(
        tmp_path,
        "EST-A,NIVEL,16/08/2013 11:45,0,41999999999999998",
        "EST-A,PRECIP,16/08/2013 11:50,",
        "EST-B,P,16/08/2013 12:00,534",
    )
    readings = read_csv_export(path, SENSORS, TZ)
    assert [(r.station, r.sensor, r.value) for r in readings] == [
        ("EST-A", "PRECIP", None),
        ("EST-B", "P", 534.0),
    ]


def test_csv_malformed_line_reports_line_number(tmp_path: Path) -> None:
    path = _csv(tmp_path, "EST-A,P,16/08/2013 11:50,1,0", "EST-A,P,no-es-fecha,2")
    with pytest.raises(ValueError, match="línea 3"):
        read_csv_export(path, SENSORS, TZ)


def test_csv_wrong_header_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "otro.csv"
    path.write_text("A,B,C,D\n", encoding="ascii")
    with pytest.raises(ValueError, match="encabezado"):
        read_csv_export(path, SENSORS, TZ)


def _xls(tmp_path: Path) -> Path:
    """Libro como el real: encabezado solo en la 1.ª hoja y fila vacía al inicio de las demás."""
    book = xlwt.Workbook()
    first = book.add_sheet("Export Worksheet")
    for col, name in enumerate(CSV_HEADER.split(",")):
        first.write(0, col, name)
    first.write(1, 0, "EST-A")
    first.write(1, 1, "P")
    first.write(1, 2, "03/08/2014 21:40")
    first.write(1, 3, 140.8)
    first.write(2, 0, "EST-A")
    first.write(2, 1, "H")
    first.write(2, 2, "03/08/2014 21:45")
    first.write(2, 3, 0.48)
    second = book.add_sheet("Sheet1")
    second.write(1, 0, "EST-A")
    second.write(1, 1, "P")
    second.write(1, 2, "03/08/2014 21:50")
    second.write(2, 0, "EST-C")
    second.write(2, 1, "P")
    second.write(2, 2, "03/08/2014 21:50")
    second.write(2, 3, "141,2")
    path = tmp_path / "export.xls"
    book.save(str(path))
    return path


def test_xls_reads_all_sheets_skipping_header_and_blank_rows(tmp_path: Path) -> None:
    readings = read_xls_export(_xls(tmp_path), SENSORS, TZ)
    assert [(r.station, r.ts.minute, r.value) for r in readings] == [
        ("EST-A", 40, pytest.approx(140.8)),
        ("EST-A", 50, None),
        ("EST-C", 50, pytest.approx(141.2)),
    ]
    assert all(r.ts.tzinfo == TZ for r in readings)


def test_xls_malformed_row_reports_sheet_and_row(tmp_path: Path) -> None:
    book = xlwt.Workbook()
    sheet = book.add_sheet("Sheet1")
    for col, value in enumerate(("EST-A", "P", "31/02/2014 25:00", 1.0)):
        sheet.write(0, col, value)
    path = tmp_path / "malo.xls"
    book.save(str(path))
    with pytest.raises(ValueError, match="hoja Sheet1, fila 1"):
        read_xls_export(path, SENSORS, TZ)
