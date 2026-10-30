"""Tests del lector de hojas de cálculo de CHIRPS (TASK-005, ADR-004 §2). Datos sintéticos."""

from datetime import date, datetime
from pathlib import Path

import openpyxl
import pytest

from climapp.data.chirps_reader import ChirpsValue, read_chirps_xlsx

Row = tuple[object, ...]


def _book(tmp_path: Path, rows: list[Row], name: str = "chirps.xlsx") -> Path:
    book = openpyxl.Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "P.Diaria"
    for row in rows:
        sheet.append(list(row))
    path = tmp_path / name
    book.save(path)
    return path


SUMMARY: list[Row] = [
    (None, None, None, None),
    ("ESTADISTICO", 598, 599, 600),
    ("MIN", 0, 0, 0),
    ("PROM", 8.9, 8.1, 6.4),
    ("MAX", 98.8, 97.8, 82.9),
]


def test_reads_daily_values_per_cell_and_drops_summary_rows(tmp_path: Path) -> None:
    rows: list[Row] = [
        ("Fecha", 598, 599, 600),
        ("1981.01.01", 2.05, 10.43, 7.96),
        ("1981.01.02", 0.46, 2.46, 1.96),
        *SUMMARY,
    ]
    values = read_chirps_xlsx(_book(tmp_path, rows))
    assert values[:3] == [
        ChirpsValue(date(1981, 1, 1), 598, pytest.approx(2.05)),
        ChirpsValue(date(1981, 1, 1), 599, pytest.approx(10.43)),
        ChirpsValue(date(1981, 1, 1), 600, pytest.approx(7.96)),
    ]
    assert len(values) == 6
    assert {v.day for v in values} == {date(1981, 1, 1), date(1981, 1, 2)}


def test_drops_extra_summary_column_without_cell_header(tmp_path: Path) -> None:
    rows: list[Row] = [
        ("FECHA", 598, 599, 600, None),
        ("1993.01.01", 4.47, 5.13, 4.60, None),
        (None, None, None, None, None),
        ("ESTADISTICO", 598, 599, 600, "GLOBAL"),
        ("MIN", 0, 0, 0, 0),
        ("PROM", 9.3, 8.4, 6.2, 7.9),
        ("MAX", 98.6, 85.3, 89.2, 98.6),
    ]
    values = read_chirps_xlsx(_book(tmp_path, rows))
    assert [(v.cell, v.precip_mm) for v in values] == [
        (598, pytest.approx(4.47)),
        (599, pytest.approx(5.13)),
        (600, pytest.approx(4.60)),
    ]


def test_file_without_summary_rows_is_read_whole(tmp_path: Path) -> None:
    rows: list[Row] = [("FECHA", 598), ("2026.09.29", 1.57), ("2026.09.30", 5.19)]
    values = read_chirps_xlsx(_book(tmp_path, rows))
    assert [v.day for v in values] == [date(2026, 9, 29), date(2026, 9, 30)]


def test_accepts_date_cells_as_well_as_text(tmp_path: Path) -> None:
    rows: list[Row] = [("FECHA", 598), (datetime(2004, 1, 1), 9.18)]
    (value,) = read_chirps_xlsx(_book(tmp_path, rows))
    assert value.day == date(2004, 1, 1)


def test_unknown_row_label_is_rejected_with_row_number(tmp_path: Path) -> None:
    rows: list[Row] = [("FECHA", 598), ("1981.01.01", 1.0), ("TOTAL", 1.0)]
    with pytest.raises(ValueError, match="fila 3"):
        read_chirps_xlsx(_book(tmp_path, rows))


def test_non_numeric_value_is_rejected(tmp_path: Path) -> None:
    rows: list[Row] = [("FECHA", 598), ("1981.01.01", "n/d")]
    with pytest.raises(ValueError, match="fila 2"):
        read_chirps_xlsx(_book(tmp_path, rows))


def test_missing_date_header_is_rejected(tmp_path: Path) -> None:
    rows: list[Row] = [("DIA", 598), ("1981.01.01", 1.0)]
    with pytest.raises(ValueError, match="encabezado"):
        read_chirps_xlsx(_book(tmp_path, rows))


def test_values_before_summary_block_are_kept_after_blank_row(tmp_path: Path) -> None:
    rows: list[Row] = [("FECHA", 598), ("1981.01.01", 1.0), *[(r[0], r[1]) for r in SUMMARY]]
    assert [v.precip_mm for v in read_chirps_xlsx(_book(tmp_path, rows))] == [1.0]
