"""Modelos de los datos de estaciones: lecturas del contador e incrementos limpios."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class Reading:
    """Lectura cruda de un sensor de una exportación.

    Attributes:
        station: identificador de la estación tal como viene en la exportación.
        sensor: nombre del sensor (p. ej. el contador acumulado de precipitación).
        ts: instante de la lectura, con zona horaria local.
        value: valor leído; `None` si la celda venía vacía.
    """

    station: str
    sensor: str
    ts: datetime
    value: float | None


class StepFlag(StrEnum):
    """Resultado de la limpieza de un paso del contador (ADR-004 §2)."""

    OK = "ok"
    RESET = "reset"
    SPIKE = "spike"
    SUSPECT = "suspect"


@dataclass(frozen=True, slots=True)
class Increment:
    """Lluvia atribuida a una lectura: diferencia con la lectura válida anterior.

    Attributes:
        ts: instante de la lectura que cierra el paso.
        mm: lluvia del paso; 0 si el paso se ignoró (`RESET` o `SPIKE`).
        flag: motivo de limpieza; `SUSPECT` conserva `mm` (SP-12).
    """

    ts: datetime
    mm: float
    flag: StepFlag
