"""Esquemas de las salidas de Muse Spark que valida la compuerta (`docs/data-model.md`).

Todos rechazan campos extra: un campo inventado es `esquema_invalido` (ADR-002 §3).
"""

import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

EXPLANATION_MAX_CHARS = 600  # ADR-002 §2
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")

EventType = Literal["lluvia", "crecida", "deslizamiento", "granizo", "sin_lluvia", "otro"]
Intensity = Literal["ninguna", "debil", "moderada", "fuerte"]  # descriptiva, SUPUESTO
Claim = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def numbers_in(text: str) -> list[float]:
    """Cifras escritas en un texto; acepta coma o punto decimal."""
    return [float(m.replace(",", ".")) for m in NUMBER.findall(text)]


class ReportStructured(BaseModel):
    """Registro estructurado de un reporte ciudadano (salida de la tarea `estructurar`)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_type: EventType
    intensity: Intensity
    observed_at: datetime
    claims: list[Claim]
    numbers_cited: list[float]

    def cited_numbers(self) -> list[float]:
        """Cifras que deben coincidir con las del sistema."""
        return list(self.numbers_cited)

    def judged_claims(self) -> list[str]:
        """Afirmaciones que revisa el juez."""
        return list(self.claims)


class ForecastExplanation(BaseModel):
    """Explicación del pronóstico (tarea `explicar`): texto corto y cifras citadas."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: Annotated[str, StringConstraints(min_length=1, max_length=EXPLANATION_MAX_CHARS)]
    numbers_cited: list[float]

    def cited_numbers(self) -> list[float]:
        """Cifras declaradas y cifras escritas en el texto: todas deben coincidir."""
        return [*self.numbers_cited, *numbers_in(self.text)]

    def judged_claims(self) -> list[str]:
        """El texto completo es la afirmación que revisa el juez."""
        return [self.text]


class JudgedClaim(BaseModel):
    """Veredicto del juez sobre una afirmación."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    evidence: str
    supported: bool


class JudgeVerdict(BaseModel):
    """Salida del juez (ADR-002 §2): `{claims: [{text, evidence, supported}]}`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    claims: list[JudgedClaim] = Field(min_length=1)

    def cited_numbers(self) -> list[float]:
        """El juez no cita cifras propias."""
        return []

    def judged_claims(self) -> list[str]:
        """El veredicto no se vuelve a juzgar."""
        return []
