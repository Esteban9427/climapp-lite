"""Tests de la confianza calculada por código (TASK-014, ADR-002 §4). Datos sintéticos."""

import json
from pathlib import Path

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from climapp.config import Settings
from climapp.verification.confidence import (
    ConfidenceWeights,
    Evidence,
    compute_confidence,
    load_station_groups,
)

# Pesos SUPUESTO del equipo (2026-10-31, ADR-002 §4): estaciones > satélite > pronóstico.
# Nivel del río (TASK-039, 2026-11-01): peso 1,0 y subida de 0,30 m en 24 h, SUPUESTO para JM
WEIGHTS = ConfidenceWeights(
    station=1.0, satellite=0.5, forecast=0.25, rain_mm=1.0, level=1.0, level_rise_m=0.30
)
GROUPS = (("EST-A",), ("EST-B", "EST-C"), ("EST-D",))


def _evidence(**kw: object) -> Evidence:
    base: dict[str, object] = {
        "report_rain": True,
        "station_mm": {"EST-A": 5.0, "EST-B": 8.0, "EST-C": 9.0, "EST-D": 0.0},
        "satellite_mm": 6.0,
        "forecast_prob": 0.4,
        "forecast_threshold": 0.13,
    }
    return Evidence(**(base | kw))  # type: ignore[arg-type]


def test_breakdown_has_one_source_per_group_and_the_other_kinds() -> None:
    conf = compute_confidence(_evidence(), GROUPS, WEIGHTS)
    assert [(s.source_id, s.kind, s.members, s.agrees) for s in conf.sources] == [
        ("EST-A", "station_group", ["EST-A"], True),
        ("EST-B+EST-C", "station_group", ["EST-B", "EST-C"], True),
        ("EST-D", "station_group", ["EST-D"], False),
        ("IMERG_E", "satellite", [], True),
        ("pronostico", "forecast", [], True),
    ]
    assert conf.independent_sources == 5
    # (1 + 1 + 0 + 0,5 + 0,25) / (1·3 + 0,5 + 0,25)
    assert conf.score == pytest.approx(2.75 / 3.75)


def test_correlated_stations_count_as_one_source() -> None:
    conf = compute_confidence(_evidence(satellite_mm=None, forecast_prob=None), GROUPS, WEIGHTS)
    assert conf.independent_sources == 3  # 4 estaciones, 3 grupos


def test_report_without_rain_agrees_with_dry_sources() -> None:
    dry = {"EST-A": 0.0, "EST-B": 0.2, "EST-C": 0.0, "EST-D": 0.0}
    conf = compute_confidence(
        _evidence(report_rain=False, station_mm=dry, satellite_mm=0.0, forecast_prob=0.05),
        GROUPS,
        WEIGHTS,
    )
    assert conf.score == 1.0


def test_forecast_agrees_when_probability_reaches_the_decision_threshold() -> None:
    conf = compute_confidence(
        _evidence(station_mm={}, satellite_mm=None, forecast_prob=0.13), GROUPS, WEIGHTS
    )
    assert [(s.kind, s.agrees) for s in conf.sources] == [("forecast", True)]


def test_group_signals_rain_if_any_member_with_data_reached_rain_mm() -> None:
    def group_agrees(station_mm: dict[str, float]) -> bool:
        conf = compute_confidence(
            _evidence(station_mm=station_mm, satellite_mm=None, forecast_prob=None),
            GROUPS,
            WEIGHTS,
        )
        (group,) = conf.sources
        return group.agrees

    assert group_agrees({"EST-B": 1.0, "EST-C": 0.0}) is True
    assert group_agrees({"EST-B": 0.9, "EST-C": 0.0}) is False


def test_station_outside_every_group_is_its_own_source() -> None:
    conf = compute_confidence(
        _evidence(station_mm={"EST-E": 3.0}, satellite_mm=None, forecast_prob=None),
        GROUPS,
        WEIGHTS,
    )
    assert [s.source_id for s in conf.sources] == ["EST-E"]


def test_without_evidence_the_score_is_zero() -> None:
    conf = compute_confidence(
        _evidence(station_mm={}, satellite_mm=None, forecast_prob=None), GROUPS, WEIGHTS
    )
    assert (conf.score, conf.independent_sources, conf.sources) == (0.0, 0, [])


def test_weights_come_from_settings(env_file: Path) -> None:
    weights = ConfidenceWeights.from_settings(Settings(_env_file=env_file))
    assert weights == WEIGHTS


def test_load_station_groups_reads_the_artifact(tmp_path: Path) -> None:
    path = tmp_path / "g.json"
    path.write_text(json.dumps({"groups": [["EST-A"], ["EST-B", "EST-C"]]}), encoding="utf-8")
    assert load_station_groups(path) == (("EST-A",), ("EST-B", "EST-C"))


# --- propiedades --------------------------------------------------------------

mm = st.floats(min_value=0, max_value=200, allow_nan=False)
stations = st.dictionaries(st.sampled_from(["EST-A", "EST-B", "EST-C", "EST-D"]), mm)
evidences = st.builds(
    Evidence,
    report_rain=st.booleans(),
    station_mm=stations,
    satellite_mm=st.none() | mm,
    forecast_prob=st.none() | st.floats(min_value=0, max_value=1),
    forecast_threshold=st.floats(min_value=0.01, max_value=0.99),
)


@given(evidences, st.sampled_from(["EST-A", "EST-B", "EST-C", "EST-D"]))
@example(  # con la media del grupo, la copia de EST-B subía la media de 0,75 a 1,0
    Evidence(True, {"EST-B": 1.5, "EST-C": 0.0}, None, None, 0.13), "EST-B"
)
def test_duplicating_a_correlated_station_never_raises_confidence(
    evidence: Evidence, station: str
) -> None:
    """Una copia de una estación, agrupada con ella, no agrega una fuente independiente."""
    if station not in evidence.station_mm:
        return
    copy = f"{station}-copia"
    groups = tuple((*g, copy) if station in g else g for g in GROUPS)
    duplicated = Evidence(
        report_rain=evidence.report_rain,
        station_mm={**evidence.station_mm, copy: evidence.station_mm[station]},
        satellite_mm=evidence.satellite_mm,
        forecast_prob=evidence.forecast_prob,
        forecast_threshold=evidence.forecast_threshold,
    )
    before = compute_confidence(evidence, GROUPS, WEIGHTS)
    after = compute_confidence(duplicated, groups, WEIGHTS)
    assert after.score <= before.score + 1e-12
    assert after.independent_sources == before.independent_sources


@given(evidences)
def test_score_is_between_zero_and_one_and_the_function_is_pure(evidence: Evidence) -> None:
    snapshot = dict(evidence.station_mm)
    first = compute_confidence(evidence, GROUPS, WEIGHTS)
    assert 0.0 <= first.score <= 1.0
    assert compute_confidence(evidence, GROUPS, WEIGHTS) == first
    assert evidence.station_mm == snapshot


@given(evidences)
def test_order_of_the_stations_does_not_matter(evidence: Evidence) -> None:
    reversed_mm = dict(reversed(list(evidence.station_mm.items())))
    other = Evidence(
        report_rain=evidence.report_rain,
        station_mm=reversed_mm,
        satellite_mm=evidence.satellite_mm,
        forecast_prob=evidence.forecast_prob,
        forecast_threshold=evidence.forecast_threshold,
    )
    assert compute_confidence(other, GROUPS, WEIGHTS) == compute_confidence(
        evidence, GROUPS, WEIGHTS
    )


def test_station_groups_outweigh_satellite_and_forecast_together() -> None:
    """Dos fuentes remotas que contradicen a un grupo de estaciones no lo superan."""
    conf = compute_confidence(
        _evidence(station_mm={"EST-A": 6.0}, satellite_mm=0.0, forecast_prob=0.01),
        GROUPS,
        WEIGHTS,
    )
    assert conf.score > 0.5


# --- nivel del río como evidencia de crecientes (TASK-039) ---------------------


def _flood(rise: float | None, **kw: object) -> Evidence:
    return _evidence(
        station_mm={},
        satellite_mm=None,
        forecast_prob=None,
        report_flood=True,
        level_rise_m=rise,
        **kw,
    )


def test_flood_report_agrees_when_the_level_rose_at_least_the_threshold() -> None:
    conf = compute_confidence(_flood(0.30), GROUPS, WEIGHTS)
    assert [(s.source_id, s.kind, s.members, s.agrees, s.weight) for s in conf.sources] == [
        ("nivel", "river_level", [], True, 1.0)
    ]
    assert conf.score == 1.0


def test_flood_report_disagrees_when_the_level_barely_moved() -> None:
    conf = compute_confidence(_flood(0.29), GROUPS, WEIGHTS)
    assert [(s.kind, s.agrees) for s in conf.sources] == [("river_level", False)]
    assert conf.score == 0.0


def test_level_is_a_source_apart_from_the_rain_sources() -> None:
    conf = compute_confidence(_evidence(report_flood=True, level_rise_m=0.5), GROUPS, WEIGHTS)
    kinds = [s.kind for s in conf.sources]
    assert kinds.count("river_level") == 1
    assert conf.independent_sources == 6  # 3 grupos + satélite + pronóstico + nivel


def test_report_that_does_not_claim_a_flood_ignores_the_level() -> None:
    with_level = _evidence(report_flood=False, level_rise_m=2.0)
    assert compute_confidence(with_level, GROUPS, WEIGHTS) == compute_confidence(
        _evidence(), GROUPS, WEIGHTS
    )


def test_level_weights_come_from_settings(env_file: Path) -> None:
    weights = ConfidenceWeights.from_settings(Settings(_env_file=env_file))
    assert (weights.level, weights.level_rise_m) == (1.0, 0.30)


def _with(evidence: Evidence, **changes: object) -> Evidence:
    fields = {
        "report_rain": evidence.report_rain,
        "station_mm": evidence.station_mm,
        "satellite_mm": evidence.satellite_mm,
        "forecast_prob": evidence.forecast_prob,
        "forecast_threshold": evidence.forecast_threshold,
        "report_flood": evidence.report_flood,
        "level_rise_m": evidence.level_rise_m,
    }
    return Evidence(**(fields | changes))  # type: ignore[arg-type]


@given(evidences, st.booleans())
def test_without_level_that_day_the_confidence_does_not_change(
    evidence: Evidence, flood: bool
) -> None:
    """Un día sin dato de nivel deja la confianza igual, afirme o no el reporte una creciente."""
    no_level = _with(evidence, report_flood=flood, level_rise_m=None)
    assert compute_confidence(no_level, GROUPS, WEIGHTS) == compute_confidence(
        _with(evidence, report_flood=False, level_rise_m=None), GROUPS, WEIGHTS
    )


@given(evidences, st.floats(min_value=0, max_value=5, allow_nan=False))
def test_level_only_matters_for_reports_that_claim_a_flood(evidence: Evidence, rise: float) -> None:
    not_flood = _with(evidence, report_flood=False, level_rise_m=rise)
    assert compute_confidence(not_flood, GROUPS, WEIGHTS) == compute_confidence(
        _with(evidence, report_flood=False, level_rise_m=None), GROUPS, WEIGHTS
    )
