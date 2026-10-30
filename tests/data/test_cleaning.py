"""Tests de la limpieza del contador acumulado (TASK-003, ADR-004 §2). Datos sintéticos."""

from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from climapp.data.cleaning import CleaningParams, compute_increments
from climapp.data.models import Reading, StepFlag

TZ = ZoneInfo("America/Bogota")
T0 = datetime(2024, 12, 31, 20, 0, tzinfo=TZ)
STEP = timedelta(minutes=10)
PARAMS = CleaningParams(
    max_step_mm=40.0,
    suspect_step_mm=30.0,
    suspect_quiet=timedelta(hours=1),
    suspect_quiet_max_mm=0.0,
)


def _series(*values: float | None, station: str = "EST-A") -> list[Reading]:
    return [
        Reading(station=station, sensor="P", ts=T0 + i * STEP, value=v)
        for i, v in enumerate(values)
    ]


def _mm(values: list[float | None], params: CleaningParams = PARAMS) -> list[float]:
    return [inc.mm for inc in compute_increments(_series(*values), params)]


def test_increments_are_differences_between_consecutive_readings() -> None:
    incs = compute_increments(_series(10.0, 10.2, 11.0, 11.0), PARAMS)
    assert [i.mm for i in incs] == pytest.approx([0.2, 0.8, 0.0])
    assert [i.ts for i in incs] == [T0 + STEP, T0 + 2 * STEP, T0 + 3 * STEP]
    assert {i.flag for i in incs} == {StepFlag.OK}


def test_reset_descent_is_ignored_and_counting_restarts() -> None:
    incs = compute_increments(_series(500.0, 500.4, 0.0, 0.6), PARAMS)
    assert [i.mm for i in incs] == pytest.approx([0.4, 0.0, 0.6])
    assert incs[1].flag is StepFlag.RESET


def test_spike_above_max_step_is_ignored() -> None:
    incs = compute_increments(_series(100.0, 100.2, 141.0, 141.2), PARAMS)
    assert [i.mm for i in incs] == pytest.approx([0.2, 0.0, 0.2])
    assert incs[1].flag is StepFlag.SPIKE


def test_step_equal_to_max_step_is_kept() -> None:
    assert _mm([0.0, 40.0]) == pytest.approx([40.0])


def test_max_step_is_configurable() -> None:
    params = replace(PARAMS, max_step_mm=5.0, suspect_step_mm=4.0, suspect_quiet=timedelta(0))
    assert _mm([0.0, 6.0, 7.0], params) == pytest.approx([0.0, 1.0])


def test_empty_values_are_skipped_and_difference_uses_last_value() -> None:
    incs = compute_increments(_series(10.0, None, 10.6), PARAMS)
    assert [(i.ts, i.mm) for i in incs] == [(T0 + 2 * STEP, pytest.approx(0.6))]


def test_unsorted_input_is_sorted_by_time() -> None:
    readings = list(reversed(_series(1.0, 1.2, 1.6)))
    assert [i.mm for i in compute_increments(readings, PARAMS)] == pytest.approx([0.2, 0.4])


def test_float_noise_is_not_rain() -> None:
    assert _mm([821.20000000000005, 821.2]) == [0.0]


def test_mixed_stations_are_rejected() -> None:
    readings = _series(1.0) + _series(2.0, station="EST-B")
    with pytest.raises(ValueError, match="una sola estación"):
        compute_increments(readings, PARAMS)


def test_empty_input_gives_no_increments() -> None:
    assert compute_increments([], PARAMS) == []


# SP-12: salto aislado >= 30 mm con 1 h sin lluvia antes y después se marca, no se borra
QUIET_HOUR = [5.0] * 7  # 7 lecturas iguales = 1 h sin lluvia


def test_isolated_jump_is_flagged_suspect_but_kept() -> None:
    incs = compute_increments(_series(*QUIET_HOUR, 43.6, *([43.6] * 6)), PARAMS)
    jump = incs[6]
    assert jump.mm == pytest.approx(38.6)
    assert jump.flag is StepFlag.SUSPECT
    assert sum(i.flag is StepFlag.SUSPECT for i in incs) == 1


def test_jump_with_rain_in_previous_hour_is_not_suspect() -> None:
    before = [5.0, 5.0, 5.0, 5.0, 5.2, 5.2, 5.2]
    incs = compute_increments(_series(*before, 43.8, *([43.8] * 6)), PARAMS)
    assert incs[6].flag is StepFlag.OK


def test_jump_with_rain_in_next_hour_is_not_suspect() -> None:
    incs = compute_increments(_series(*QUIET_HOUR, 43.6, 43.6, 44.0, 44.0, 44, 44, 44), PARAMS)
    assert incs[6].flag is StepFlag.OK


def test_jump_below_suspect_threshold_is_not_suspect() -> None:
    incs = compute_increments(_series(*QUIET_HOUR, 34.9, *([34.9] * 6)), PARAMS)
    assert incs[6].flag is StepFlag.OK


def test_jump_without_readings_after_is_not_suspect() -> None:
    incs = compute_increments(_series(*QUIET_HOUR, 43.6), PARAMS)
    assert incs[-1].flag is StepFlag.OK


def test_jump_with_incomplete_quiet_hour_is_not_suspect() -> None:
    incs = compute_increments(_series(5.0, 5.0, 43.6, *([43.6] * 6)), PARAMS)
    assert incs[1].flag is StepFlag.OK


# Forma del caso real de SP-12: hora previa en cero y 1,8 mm entre 40 y 60 min después
AFTER_WITH_DRIZZLE = [43.6, 43.6, 43.6, 44.2, 45.2, 45.4, 45.4]


def test_literal_rule_does_not_flag_jump_with_drizzle_after() -> None:
    incs = compute_increments(_series(*QUIET_HOUR, *AFTER_WITH_DRIZZLE), PARAMS)
    assert incs[6].flag is StepFlag.OK


def test_quiet_tolerance_flags_jump_with_drizzle_after() -> None:
    params = replace(PARAMS, suspect_quiet_max_mm=2.0)
    incs = compute_increments(_series(*QUIET_HOUR, *AFTER_WITH_DRIZZLE), params)
    assert incs[6].flag is StepFlag.SUSPECT
    assert incs[6].mm == pytest.approx(38.6)


def test_quiet_tolerance_applies_to_each_window_separately() -> None:
    params = replace(PARAMS, suspect_quiet_max_mm=2.0)
    before = [5.0, 5.0, 5.0, 6.0, 6.5, 7.6, 7.6]  # 2,6 mm en la hora previa
    incs = compute_increments(_series(*before, 46.2, *([46.2] * 6)), params)
    assert incs[6].flag is StepFlag.OK


# Huecos: un paso entre lecturas separadas por más de max_gap no es lluvia atribuible


def _at(*points: tuple[datetime, float]) -> list[Reading]:
    return [Reading("raw-a", "P", ts, v) for ts, v in points]


def test_step_across_a_long_gap_is_not_rain() -> None:
    incs = compute_increments(_at((T0, 10.0), (T0 + timedelta(days=3), 35.0)), PARAMS)
    assert [(i.mm, i.flag) for i in incs] == [(0.0, StepFlag.GAP)]


def test_step_across_a_gap_within_the_limit_is_rain() -> None:
    incs = compute_increments(_at((T0, 10.0), (T0 + timedelta(minutes=20), 10.4)), PARAMS)
    assert [(i.mm, i.flag) for i in incs] == [(pytest.approx(0.4), StepFlag.OK)]


def test_step_just_over_the_limit_is_a_gap() -> None:
    incs = compute_increments(_at((T0, 10.0), (T0 + timedelta(minutes=30), 10.4)), PARAMS)
    assert incs[0].flag is StepFlag.GAP


def test_reset_after_a_gap_is_a_gap_and_counting_restarts() -> None:
    later = T0 + timedelta(days=2)
    incs = compute_increments(_at((T0, 500.0), (later, 0.0), (later + STEP, 0.4)), PARAMS)
    assert [(i.mm, i.flag) for i in incs] == [
        (0.0, StepFlag.GAP),
        (pytest.approx(0.4), StepFlag.OK),
    ]


def test_max_gap_is_configurable() -> None:
    params = replace(PARAMS, max_gap=timedelta(hours=2))
    incs = compute_increments(_at((T0, 10.0), (T0 + timedelta(minutes=90), 11.0)), params)
    assert incs[0].flag is StepFlag.OK


def test_gap_inside_a_quiet_window_prevents_suspect() -> None:
    before = [Reading("raw-a", "P", T0 + i * STEP, 5.0) for i in (0, 1, 4, 5, 6)]  # hueco 30 min
    jump = [Reading("raw-a", "P", T0 + i * STEP, 43.6) for i in range(7, 14)]
    incs = compute_increments(before + jump, PARAMS)
    assert next(i for i in incs if i.mm > 30).flag is StepFlag.OK
