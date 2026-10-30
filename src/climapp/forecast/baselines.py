"""Líneas base del pronóstico: climatología y persistencia (ADR-001 §8)."""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta

DAYS_PER_YEAR = 365  # distancia circular entre días del año (el 29-feb queda a 1 día)


def _doy(day: date) -> int:
    """Día del año (1-366)."""
    return day.timetuple().tm_yday


def _doy_distance(a: int, b: int) -> int:
    """Distancia circular entre dos días del año."""
    diff = abs(a - b)
    return min(diff, DAYS_PER_YEAR - diff)


def climatology_probs(
    train: Mapping[date, bool | None], targets: Iterable[date], window_days: int
) -> list[float]:
    """Frecuencia del evento en el entrenamiento alrededor del día del año de cada fecha.

    Args:
        train: observación del evento por día de entrenamiento (`None` = sin dato).
        targets: fechas para las que se pide la probabilidad.
        window_days: semiancho de la ventana (`CLIMATOLOGY_WINDOW_DAYS`, ±15).

    Returns:
        Una probabilidad por fecha, en el mismo orden.

    Raises:
        ValueError: si no hay días de entrenamiento con dato en la ventana.
    """
    counts: Counter[int] = Counter()
    events: Counter[int] = Counter()
    for day, event in train.items():
        if event is not None:
            counts[_doy(day)] += 1
            events[_doy(day)] += event
    probs: list[float] = []
    for target in targets:
        near = [d for d in counts if _doy_distance(d, _doy(target)) <= window_days]
        total = sum(counts[d] for d in near)
        if not total:
            msg = f"sin días de entrenamiento en la ventana de {target}"
            raise ValueError(msg)
        probs.append(sum(events[d] for d in near) / total)
    return probs


@dataclass(frozen=True, slots=True)
class Persistence:
    """Persistencia: mañana se repite lo de hoy.

    Attributes:
        prob_after_event: P(evento mañana | evento hoy) en el entrenamiento.
        prob_after_no_event: P(evento mañana | sin evento hoy) en el entrenamiento.
    """

    prob_after_event: float
    prob_after_no_event: float

    def binary(self, today: bool) -> float:
        """Pronóstico determinista: 1 si hoy hubo evento, si no 0 (para POD, FAR y CSI)."""
        return 1.0 if today else 0.0

    def prob(self, today: bool) -> float:
        """Frecuencia condicional del entrenamiento (para Brier y AUC)."""
        return self.prob_after_event if today else self.prob_after_no_event


def fit_persistence(observed: Mapping[date, bool | None]) -> Persistence:
    """Ajusta la persistencia con los pares (hoy, mañana) con dato en ambos días.

    Raises:
        ValueError: si no hay pares tras un evento y tras un no evento.
    """
    after: dict[bool, list[bool]] = {True: [], False: []}
    for day, today in observed.items():
        tomorrow = observed.get(day + timedelta(days=1))
        if today is not None and tomorrow is not None:
            after[today].append(tomorrow)
    if not after[True] or not after[False]:
        msg = "faltan pares (hoy, mañana) tras un evento o tras un no evento"
        raise ValueError(msg)
    return Persistence(
        prob_after_event=sum(after[True]) / len(after[True]),
        prob_after_no_event=sum(after[False]) / len(after[False]),
    )
