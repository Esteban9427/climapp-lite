"""Reportes de ejemplo de la demo (`DEMO_REPORTS_FILE`, versionado).

Solo se ofrecen con `DEMO_FALLBACK=1`: sus textos son los que se grabaron contra Muse, así
que el fallback los verifica con coincidencia exacta. Las coordenadas no se versionan: el
botón usa el centro del polígono de la cuenca, que vive fuera de git.
"""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class DemoReport(BaseModel):
    """Un reporte de ejemplo: título del botón y texto exacto grabado."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    titulo: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=1000)


_DEMO = TypeAdapter(list[DemoReport])


def load_demo_reports(path: Path) -> list[DemoReport]:
    """Lee los ejemplos de la demo.

    Raises:
        OSError: si el archivo no se puede leer.
        pydantic.ValidationError: si el archivo no es válido.
    """
    return _DEMO.validate_json(path.read_bytes())
