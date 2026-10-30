"""Serie sintética de la cuenca para los tests del modelo (sin datos reales)."""

import random
from datetime import date, timedelta

from climapp.data.models import DailyPrecip

START = date(2013, 10, 1)
END = date(2026, 10, 31)


def synthetic_rows(seed: int = 7, start: date = START, end: date = END) -> list[DailyPrecip]:
    """Dos estaciones con lluvia persistente (AR(1)) para que haya señal aprendible."""
    rng = random.Random(seed)
    rows: list[DailyPrecip] = []
    wet = 0.0
    for i in range((end - start).days + 1):
        day = start + timedelta(days=i)
        wet = 0.7 * wet + rng.expovariate(1 / 6)
        for series, factor in (("EST-A", 1.0), ("EST-B", 1.2)):
            mm = round(wet * factor * rng.uniform(0.6, 1.4), 1)
            missing = series == "EST-B" and rng.random() < 0.1
            rows.append(_row(day, series, None if missing else mm))
    return rows


def _row(day: date, series: str, mm: float | None) -> DailyPrecip:
    return DailyPrecip(
        date=day,
        series_id=series,
        precip_mm=mm,
        n_readings=144 if mm is not None else 50,
        valid=mm is not None,
        imputed=False,
        source_hash="h",
        n_suspect=0,
        n_gap=0,
    )
