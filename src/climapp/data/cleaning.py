"""Limpieza del contador acumulado de lluvia de una estación (ADR-004 §2).

Función pura: incremento = diferencia con la lectura válida anterior. Se ignoran los
descensos (reinicios) y los aumentos mayores a `max_step_mm` (picos; umbral SUPUESTO).
Un salto aislado de al menos `suspect_step_mm`, con `suspect_quiet` sin lluvia antes y
después, se marca `SUSPECT` sin borrarse (SP-12, SUPUESTO pendiente de JM).
"""

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from itertools import pairwise

from climapp.data.days import step_crosses_day
from climapp.data.models import Increment, Reading, StepFlag

# Los valores del contador traen ruido de coma flotante (p. ej. 821.20000000000005);
# el pluviómetro mide en décimas de mm, así que 1e-6 mm es ruido, no lluvia.
FLOAT_TOLERANCE_MM = 1e-6


@dataclass(frozen=True, slots=True)
class CleaningParams:
    """Umbrales de limpieza, normalmente tomados de `Settings`.

    Attributes:
        max_step_mm: aumento máximo aceptado en un paso (`MAX_STEP_MM`, SUPUESTO).
        suspect_step_mm: salto mínimo que puede marcarse `SUSPECT` (`SUSPECT_STEP_MM`).
        suspect_quiet: tiempo sin lluvia exigido antes y después (`SUSPECT_QUIET_MIN`).
        suspect_quiet_max_mm: lluvia máxima tolerada en cada ventana de calma
            (`SUSPECT_QUIET_MAX_MM`; 0 es la regla literal de SP-12).
        max_gap: separación máxima entre lecturas sin marca de hueco (`MAX_GAP_MIN`,
            SUPUESTO); un paso más largo es `GAP` (0 mm) si cruza el día local y
            `GAP_INTRADAY` (conserva la lluvia) si no.
    """

    max_step_mm: float
    suspect_step_mm: float
    suspect_quiet: timedelta
    suspect_quiet_max_mm: float
    max_gap: timedelta


def _classify(diff: float, max_step_mm: float) -> tuple[float, StepFlag]:
    """Lluvia y bandera de un paso del contador."""
    if diff < -FLOAT_TOLERANCE_MM:
        return 0.0, StepFlag.RESET
    if diff > max_step_mm:
        return 0.0, StepFlag.SPIKE
    return (diff if diff > FLOAT_TOLERANCE_MM else 0.0), StepFlag.OK


def _valued_points(readings: Sequence[Reading]) -> list[tuple[datetime, float]]:
    """Puntos `(instante, valor)` de las lecturas con valor, en orden temporal."""
    return sorted((r.ts, r.value) for r in readings if r.value is not None)


def _step(prev_ts: datetime, ts: datetime, diff: float, params: CleaningParams) -> Increment:
    """Clasifica un paso del contador, teniendo en cuenta los huecos (ADR-004 §2).

    Un hueco que cruza el día local es `GAP`: no se sabe a qué día atribuir la lluvia.
    Dentro del mismo día el contador acumulado sí la atribuye bien, así que se conserva
    como `GAP_INTRADAY` salvo que el paso sea un reinicio o un pico.
    """
    long_gap = ts - prev_ts > params.max_gap
    if long_gap and step_crosses_day(prev_ts, ts):
        return Increment(ts=ts, mm=0.0, flag=StepFlag.GAP)
    mm, flag = _classify(diff, params.max_step_mm)
    if long_gap and flag is StepFlag.OK:
        flag = StepFlag.GAP_INTRADAY
    return Increment(ts=ts, mm=mm, flag=flag)


def _raw_increments(
    points: Sequence[tuple[datetime, float]], params: CleaningParams
) -> list[Increment]:
    """Incrementos clasificados entre puntos consecutivos."""
    return [_step(t0, t1, v1 - v0, params) for (t0, v0), (t1, v1) in pairwise(points)]


def _is_isolated(
    incs: Sequence[Increment], times: Sequence[datetime], i: int, params: CleaningParams
) -> bool:
    """`True` si cada ventana de calma alrededor de `incs[i]` tiene a lo sumo la tolerancia.

    Un incremento con instante `t` es lluvia caída hasta `t`, así que la lluvia de la
    hora previa son los incrementos en `(ts - quiet, ts)` y la de la posterior, los de
    `(ts, ts + quiet]`. Cada ventana se compara por separado con `suspect_quiet_max_mm`.
    Un hueco (`GAP`) dentro de una ventana impide afirmar que no llovió.
    """
    ts, quiet = incs[i].ts, params.suspect_quiet
    limit = params.suspect_quiet_max_mm + FLOAT_TOLERANCE_MM
    before = incs[bisect_right(times, ts - quiet) : i]
    after = incs[i + 1 : bisect_right(times, ts + quiet)]
    if any(inc.flag is StepFlag.GAP for inc in (*before, *after)):
        return False
    return sum(inc.mm for inc in before) <= limit and sum(inc.mm for inc in after) <= limit


def _flag_suspects(
    incs: list[Increment], series: tuple[datetime, datetime], params: CleaningParams
) -> list[Increment]:
    """Marca `SUSPECT` los saltos aislados (SP-12), conservando su lluvia.

    Solo se marca si las lecturas cubren las dos ventanas completas: la serie debe
    empezar antes de `ts - quiet` y terminar después de `ts + quiet`.
    """
    times = [inc.ts for inc in incs]
    quiet = params.suspect_quiet
    flagged = list(incs)
    for i, inc in enumerate(incs):
        if inc.flag is not StepFlag.OK or inc.mm < params.suspect_step_mm:
            continue
        covered = series[0] <= inc.ts - quiet and series[1] >= inc.ts + quiet
        if covered and _is_isolated(incs, times, i, params):
            flagged[i] = replace(inc, flag=StepFlag.SUSPECT)
    return flagged


def compute_increments(readings: Sequence[Reading], params: CleaningParams) -> list[Increment]:
    """Calcula los incrementos limpios del contador de una estación.

    Args:
        readings: lecturas de una sola estación, en cualquier orden; las vacías se saltan.
        params: umbrales de limpieza.

    Returns:
        Un incremento por lectura con valor, salvo la primera, en orden temporal.

    Raises:
        ValueError: si las lecturas son de más de una estación.
    """
    if len({r.station for r in readings}) > 1:
        msg = "compute_increments espera lecturas de una sola estación"
        raise ValueError(msg)
    points = _valued_points(readings)
    incs = _raw_increments(points, params)
    if not incs:
        return incs
    return _flag_suspects(incs, (points[0][0], points[-1][0]), params)
