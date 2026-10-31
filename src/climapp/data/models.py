"""Modelos de los datos de estaciones: lecturas del contador e incrementos limpios."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


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
    GAP = "gap"
    GAP_INTRADAY = "gap_intraday"


GAP_FLAGS = frozenset({StepFlag.GAP, StepFlag.GAP_INTRADAY})


@dataclass(frozen=True, slots=True)
class Increment:
    """Lluvia atribuida a una lectura: diferencia con la lectura válida anterior.

    Attributes:
        ts: instante de la lectura que cierra el paso.
        mm: lluvia del paso; 0 si el paso se ignoró (`RESET`, `SPIKE` o `GAP`).
        flag: motivo de limpieza; `SUSPECT` conserva `mm` para auditoría, pero la tabla
            diaria no lo suma (SP-12 [JM 2026-10-30]). Un paso entre
            lecturas separadas por más de `MAX_GAP_MIN` es `GAP` (0 mm) si cruza el día
            local y `GAP_INTRADAY` (conserva `mm`) si queda dentro del mismo día.
    """

    ts: datetime
    mm: float
    flag: StepFlag


class DailyPrecip(BaseModel):
    """Fila de la tabla diaria de precipitación (`docs/data-model.md`).

    Attributes:
        date: día local (America/Bogota).
        series_id: `EST-A`…`EST-D` (o una serie satelital).
        precip_mm: lluvia del día; `None` si el día no es válido.
        n_readings: lecturas con valor en el día (solo estaciones).
        valid: `n_readings >= MIN_READINGS` (SUPUESTO, SP-8).
        imputed: `True` si se rellenó con vecinas; nunca entra a la evaluación.
        source_hash: SHA-256 de los archivos crudos de origen, separados por coma.
        n_suspect: saltos `suspect` del día (SP-12 [JM 2026-10-30]).
        suspect_mm: lluvia de esos saltos; no se suma a `precip_mm`, queda para auditoría.
        n_gap: pasos sobre huecos mayores a `MAX_GAP_MIN`; solo los que cruzan el día
            (`GAP`) se anulan, los del mismo día (`GAP_INTRADAY`) conservan su lluvia.
    """

    model_config = ConfigDict(frozen=True)

    date: date
    series_id: str
    precip_mm: float | None
    n_readings: int | None = Field(ge=0)
    valid: bool
    imputed: bool
    source_hash: str
    n_suspect: int = Field(ge=0)
    suspect_mm: float = Field(ge=0)
    n_gap: int = Field(ge=0)
