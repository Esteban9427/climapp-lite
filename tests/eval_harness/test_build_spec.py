"""Tests de la especificación del set de evaluación de reportes (TASK-021).

El módulo vive en `eval-harness/` (no es parte de la app), así que se carga por ruta.
"""

import importlib.util
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "eval-harness" / "build_spec.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_spec", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_spec"] = module
    spec.loader.exec_module(module)
    return module


bs = _load()

RULES = bs.LabelRules(
    event_rain_mm=20.0, event_rise_m=0.30, rain_day_mm=1.0, dry_rise_m=0.05, claimed_rise_m=5.0
)


def _facts(rain: float | None, rise: float | None, n: int = 3) -> object:
    return bs.DayFacts(
        day=date(2024, 4, 28),
        rain_mm=rain,
        n_stations=n if rain is not None else 0,
        rise_m=rise,
        imerg_mm=None,
        level_event=False,
        peak_time=None,
    )


@pytest.mark.parametrize(
    ("rain", "rise", "expected"),
    [(25.0, 0.10, True), (5.0, 0.35, True), (19.9, 0.29, False), (0.0, 0.70, False)],
)
def test_event_day_needs_threshold_and_some_rain(rain: float, rise: float, expected: bool) -> None:
    assert bs.is_event_day(_facts(rain, rise), RULES) is expected


@pytest.mark.parametrize(
    ("rain", "rise", "expected"),
    [(0.5, 0.01, True), (1.0, 0.01, False), (0.5, 0.05, False), (0.5, None, False)],
)
def test_dry_day_needs_little_rain_and_known_flat_level(
    rain: float, rise: float | None, expected: bool
) -> None:
    assert bs.is_dry_day(_facts(rain, rise), RULES) is expected


@pytest.mark.parametrize(
    ("kind", "rain", "rise", "label"),
    [
        ("coherente", 30.0, 0.5, "verdadero"),
        ("dificil", 30.0, 0.5, "verdadero"),
        ("exagerado", 30.0, 0.5, "exagerado"),
        ("falso", 0.2, 0.01, "falso"),
    ],
)
def test_label_comes_from_kind_and_data(kind: str, rain: float, rise: float, label: str) -> None:
    assert bs.expected_label(kind, _facts(rain, rise), RULES) == label


@pytest.mark.parametrize(
    ("kind", "rain", "rise"),
    [("coherente", 0.2, 0.01), ("falso", 30.0, 0.5), ("exagerado", 30.0, 6.0)],
)
def test_label_refuses_rows_the_data_contradicts(kind: str, rain: float, rise: float) -> None:
    with pytest.raises(bs.SpecError):
        bs.expected_label(kind, _facts(rain, rise), RULES)


def test_parse_events_reads_windows_and_peak(tmp_path: Path) -> None:
    path = tmp_path / "eventos.csv"
    path.write_text(
        "#,Periodo lluvia,Precip. (mm),Nivel mín.,Nivel máx.,Nivel medio,Nivel previo,"
        "Subida (m),Hora del pico\n"
        "1,2025-02-15 → 2025-02-17,143.2,1.13,1.69,1.36,1.13,+0.56,2025-02-17 19:40\n"
        "2,2014-09-04 → 2014-09-05,126.8,0.49,0.51,0.50,0.51,—,(casi sin respuesta)\n",
        encoding="utf-8",
    )
    events = bs.read_events(path)
    assert events[0].start == date(2025, 2, 15)
    assert events[0].end == date(2025, 2, 17)
    assert events[0].peak is not None
    assert events[0].peak.isoformat() == "2025-02-17T19:40:00"
    assert events[1].peak is None


def _calendar() -> list[object]:
    """Cuatro años sintéticos: un evento cada 7 días y el resto seco."""
    facts = []
    day = date(2023, 1, 1)
    while day <= date(2026, 10, 31):
        wet = day.toordinal() % 7 == 0
        facts.append(
            bs.DayFacts(
                day=day,
                rain_mm=30.0 if wet else 0.2,
                n_stations=3,
                rise_m=0.5 if wet else 0.01,
                imerg_mm=None,
                level_event=wet and day.toordinal() % 14 == 0,
                peak_time=None,
            )
        )
        day += timedelta(days=1)
    return facts


MIX = bs.Mix(coherente=25, exagerado=10, falso=10, dificil=5)
EXCLUDED = frozenset({date(2026, 10, 1), date(2026, 10, 2)})
SECTORS = ("alta", "media-alta", "media", "piedemonte", "La Vorágine")


def _rows() -> list[dict[str, object]]:
    return bs.build_rows(_calendar(), RULES, MIX, EXCLUDED, SECTORS, seed=21)


def test_build_rows_has_the_requested_mix() -> None:
    rows = _rows()
    kinds = [r["clase"] for r in rows]
    assert len(rows) == 50
    assert {k: kinds.count(k) for k in set(kinds)} == {
        "coherente": 25,
        "exagerado": 10,
        "falso": 10,
        "dificil": 5,
    }
    assert len({r["id"] for r in rows}) == 50


def test_build_rows_is_deterministic_and_skips_demo_days() -> None:
    rows = _rows()
    assert rows == _rows()
    assert not {date.fromisoformat(str(r["fecha"])) for r in rows} & EXCLUDED


def test_exaggerated_rows_reuse_coherent_days() -> None:
    rows = _rows()
    coherent = {r["fecha"] for r in rows if r["clase"] == "coherente"}
    assert {r["fecha"] for r in rows if r["clase"] == "exagerado"} <= coherent


def test_rows_spread_over_test_years_and_known_sectors() -> None:
    rows = _rows()
    assert {str(r["fecha"])[:4] for r in rows} == {"2023", "2024", "2025", "2026"}
    assert {r["sector"] for r in rows} <= set(SECTORS)


def test_rows_carry_facts_and_an_instruction_without_station_ids() -> None:
    for row in _rows():
        hechos = row["hechos"]
        assert isinstance(hechos, dict)
        assert {"lluvia_media_cuenca_mm", "subida_nivel_24h_m", "imerg_early_mm"} <= set(hechos)
        text = json.dumps(row, ensure_ascii=False)
        assert "EST-" not in text
        assert str(row["instruccion_texto"]).strip()


def test_hard_rows_cite_a_plausible_number() -> None:
    hard = [r for r in _rows() if r["clase"] == "dificil"]
    assert all(
        any(ch.isdigit() for ch in str(r["instruccion_texto"]))
        or "medio" in str(r["instruccion_texto"])
        for r in hard
    )


def test_build_rows_fails_when_the_data_is_short() -> None:
    with pytest.raises(bs.SpecError):
        bs.build_rows(_calendar()[:30], RULES, MIX, EXCLUDED, SECTORS, seed=21)
