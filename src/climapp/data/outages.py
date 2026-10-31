"""Periodos de falla conocidos de una serie, confirmados por el experto (SP-13).

El criterio de día válido (`MIN_READINGS`) no detecta un sensor que transmite lecturas
completas pero no registra lluvia. Esos periodos se declaran en un archivo versionado
(`KNOWN_OUTAGES_FILE`) con su motivo y su fuente, y sus días quedan inválidos.
"""

from collections.abc import Iterable, Sequence
from datetime import date
from pathlib import Path
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, StringConstraints, TypeAdapter, model_validator

from climapp.data.models import DailyPrecip
from climapp.logging import get_logger

log = get_logger(__name__)

PublicSeriesId = Annotated[str, StringConstraints(pattern=r"^EST-[A-Z]$")]
NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class KnownOutage(BaseModel):
    """Periodo en que una serie no registró bien la lluvia.

    Attributes:
        series_id: identificador público `EST-x` (nunca el nombre real, ADR-004).
        desde: primer día local afectado, incluido.
        hasta: último día local afectado, incluido.
        motivo: causa de la falla.
        fuente: quién la confirmó y cuándo (p. ej. "JM 2026-10-30").

    Raises:
        pydantic.ValidationError: si falta un campo, uno está vacío o `desde > hasta`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    series_id: PublicSeriesId
    desde: date
    hasta: date
    motivo: NonBlank
    fuente: NonBlank

    @model_validator(mode="after")
    def _chronological(self) -> Self:
        """Exige `desde <= hasta`."""
        if self.desde > self.hasta:
            msg = "desde debe ser anterior o igual a hasta"
            raise ValueError(msg)
        return self

    def covers(self, row: DailyPrecip) -> bool:
        """`True` si la fila es de esta serie y cae dentro del periodo."""
        return row.series_id == self.series_id and self.desde <= row.date <= self.hasta


_OUTAGES = TypeAdapter(list[KnownOutage])


def load_known_outages(path: Path) -> list[KnownOutage]:
    """Lee el registro versionado de periodos de falla (`KNOWN_OUTAGES_FILE`).

    Raises:
        OSError: si el archivo no se puede leer.
        pydantic.ValidationError: si el JSON o algún registro no es válido.
    """
    return _OUTAGES.validate_json(path.read_bytes())


def apply_outages(rows: Iterable[DailyPrecip], outages: Sequence[KnownOutage]) -> list[DailyPrecip]:
    """Marca inválidos, sin `precip_mm`, los días que caen en un periodo de falla.

    Args:
        rows: filas de la tabla diaria.
        outages: periodos de falla conocidos.

    Returns:
        Las filas en el mismo orden; las afectadas conservan `n_readings` y sus contadores.
    """
    result: list[DailyPrecip] = []
    invalidated = 0
    for row in rows:
        if any(outage.covers(row) for outage in outages):
            invalidated += row.valid
            result.append(row.model_copy(update={"valid": False, "precip_mm": None}))
        else:
            result.append(row)
    log.info("daily.outages_applied", outages=len(outages), invalidated=invalidated)
    return result
