"""Convención de día local para las lecturas del contador (ADR-004 §1)."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def local_day(ts: datetime, tz: ZoneInfo | None = None) -> date:
    """Día local al que pertenece una lectura (la de las 00:00 cierra el día anterior).

    Args:
        ts: instante de la lectura, con zona horaria.
        tz: zona local; si es `None` se usa la zona de `ts`.

    Returns:
        La fecha local del paso que cierra la lectura.
    """
    local = ts.astimezone(tz) if tz else ts
    if local.timetz().replace(tzinfo=None) == time(0, 0):
        return local.date() - timedelta(days=1)
    return local.date()


def step_crosses_day(prev_ts: datetime, ts: datetime) -> bool:
    """`True` si el paso `(prev_ts, ts]` abarca más de un día local.

    El paso queda dentro del día de `ts` solo si `prev_ts` no es anterior a las 00:00
    de ese día (la lectura de las 00:00 cierra el día anterior).
    """
    day_start = datetime.combine(local_day(ts), time(0, 0), tzinfo=ts.tzinfo)
    return prev_ts < day_start
