"""Etiqueta visible según la confianza de un reporte verificado (ADR-002 §4, docs/design.md).

`verificado` solo dice que el texto pasó la compuerta; la etiqueta dice si los datos lo
respaldan, para que un reporte con confianza baja no se lea como confirmado. Solo cambia
la vista: el contrato de la API no tiene etiqueta.
"""

from dataclasses import dataclass

from climapp.config import Settings


@dataclass(frozen=True, slots=True)
class AgreementThresholds:
    """Cortes de la etiqueta (SUPUESTO, ADR-002 §4).

    Attributes:
        high: confianza mínima para "Coincide con los datos" (`AGREEMENT_HIGH`).
        low: confianza mínima para "Coincidencia parcial" (`AGREEMENT_LOW`).
    """

    high: float
    low: float

    @classmethod
    def from_settings(cls, settings: Settings) -> "AgreementThresholds":
        """Toma `AGREEMENT_HIGH` y `AGREEMENT_LOW`."""
        return cls(high=settings.agreement_high, low=settings.agreement_low)


@dataclass(frozen=True, slots=True)
class AgreementLabel:
    """Texto de la insignia y su clase CSS."""

    text: str
    css: str


def agreement_label(score: float, thresholds: AgreementThresholds) -> AgreementLabel:
    """Etiqueta para una confianza entre 0 y 1.

    Args:
        score: confianza calculada por código.
        thresholds: cortes `high` y `low` (cada corte pertenece al tramo de arriba).

    Returns:
        "Coincide con los datos", "Coincidencia parcial" o "No coincide con los datos".
    """
    if score >= thresholds.high:
        return AgreementLabel("Coincide con los datos", "badge-ok")
    if score >= thresholds.low:
        return AgreementLabel("Coincidencia parcial", "badge-partial")
    return AgreementLabel("No coincide con los datos", "badge-danger")
