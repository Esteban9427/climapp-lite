"""Muestras (emisión t → objetivo t + 1) y partición temporal (ADR-001 §9).

Cada muestra pertenece al periodo de su **fecha objetivo**: así ningún día de prueba
aparece como etiqueta en el entrenamiento ni en la calibración.
"""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from climapp.config import TargetRule
from climapp.forecast.features import feature_row
from climapp.forecast.target import BasinDay, observed_event

Part = Literal["train", "valid", "test"]


@dataclass(frozen=True, slots=True)
class Sample:
    """Una emisión con sus variables, lo observado mañana y lo observado hoy."""

    issue_date: date
    target_date: date
    x: tuple[float, ...]
    observed: bool | None
    today_observed: bool | None
    imputed: bool


@dataclass(frozen=True, slots=True)
class Periods:
    """Límites de la partición temporal (fechas objetivo, inclusivas)."""

    train_start: date
    train_end: date
    valid_end: date
    test_end: date

    def __post_init__(self) -> None:
        """Valida el orden de los límites.

        Raises:
            ValueError: si los periodos no son cronológicos.
        """
        if not self.train_start < self.train_end < self.valid_end < self.test_end:
            msg = "los periodos deben ser cronológicos y sin solaparse"
            raise ValueError(msg)

    def part(self, target: date) -> Part | None:
        """Periodo de una fecha objetivo; `None` si queda fuera de todos."""
        if self.train_start <= target <= self.train_end:
            return "train"
        if target <= self.train_end:
            return None
        if target <= self.valid_end:
            return "valid"
        return "test" if target <= self.test_end else None


def build_samples(
    basin: Mapping[date, BasinDay],
    chirps: Mapping[date, float],
    threshold_mm: float,
    rule: TargetRule,
    imputed_dates: Collection[date] = frozenset(),
) -> list[Sample]:
    """Una muestra por día de la cuenca, usado como fecha de emisión.

    Args:
        basin: agregados de la cuenca por día.
        chirps: media diaria de CHIRPS.
        threshold_mm: umbral del evento.
        rule: regla del objetivo.
        imputed_dates: días con algún valor imputado (no entran a la evaluación).
    """

    def event(day: date) -> bool | None:
        found = basin.get(day)
        return None if found is None else observed_event(found, rule, threshold_mm)

    samples: list[Sample] = []
    for issue in basin:
        row = feature_row(issue, basin, chirps)
        target = issue + timedelta(days=1)
        samples.append(
            Sample(issue, target, row.values, event(target), event(issue), target in imputed_dates)
        )
    return samples


def split_samples(samples: Sequence[Sample], periods: Periods) -> dict[Part, list[Sample]]:
    """Reparte las muestras en entrenamiento, validación y prueba por fecha objetivo."""
    parts: dict[Part, list[Sample]] = {"train": [], "valid": [], "test": []}
    for sample in samples:
        part = periods.part(sample.target_date)
        if part is not None:
            parts[part].append(sample)
    return parts
