"""Comprobaciones deterministas de la compuerta, sin LLM (ADR-002 §3.1).

Orden: `finish_reason == "stop"` → contenido no vacío → esquema → cifras iguales a las
del modelo → sin datos personales en las afirmaciones → solo herramientas permitidas. Se
reportan todos los motivos que fallen, en ese orden; el esquema, las cifras y los datos
personales solo se pueden revisar si hay contenido.
"""

import json
import re
from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, Self

from pydantic import ValidationError

from climapp.verification.muse import MuseReply

ALLOWED_TOOLS: frozenset[str] = frozenset()  # lista blanca de v1: vacía (ADR-002 §3)
NUMBER_TOLERANCE = 1e-9  # las cifras ya vienen redondeadas: se exige igualdad
# Datos personales en las afirmaciones (decisión del equipo, 2026-10-31): celulares (3xx) y
# fijos (60x) de Colombia con indicativo opcional, correos y placas (ABC123, ABC12D).
PERSONAL_DATA = (
    re.compile(r"(?<!\d)(?:\+?57[\s.-]?)?(?:3\d{2}|60\d)[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)"),
    re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    re.compile(r"\b[A-Z]{3}[\s-]?\d{2}[0-9A-Z]\b"),
)
FENCE = re.compile(r"^\s*```(?:json)?\s*\n(?P<body>.*)\n\s*```\s*$", re.DOTALL)


class Reason(StrEnum):
    """Motivos de rechazo de un intento (`docs/data-model.md`, VerificationAttempt)."""

    RESPUESTA_INCOMPLETA = "respuesta_incompleta"
    RESPUESTA_VACIA = "respuesta_vacia"
    ESQUEMA_INVALIDO = "esquema_invalido"
    CIFRA_NO_COINCIDE = "cifra_no_coincide"
    DATO_PERSONAL = "dato_personal"
    HERRAMIENTA_NO_PERMITIDA = "herramienta_no_permitida"
    AFIRMACION_SIN_EVIDENCIA = "afirmacion_sin_evidencia"


class CitesNumbers(Protocol):
    """Salida validable: modelo Pydantic con sus cifras citadas y sus afirmaciones."""

    @classmethod
    def model_validate_json(cls, json_data: str) -> Self:
        """Valida el JSON contra el esquema."""
        ...

    def cited_numbers(self) -> list[float]:
        """Cifras que deben coincidir con las del sistema."""
        ...

    def judged_claims(self) -> list[str]:
        """Afirmaciones que revisa el juez."""
        ...


@dataclass(frozen=True, slots=True)
class CheckResult[T]:
    """Resultado de las comprobaciones: motivos que fallaron y la salida validada."""

    reasons: tuple[Reason, ...]
    parsed: T | None

    @property
    def passed(self) -> bool:
        """`True` si no falló ninguna comprobación."""
        return not self.reasons


def _unfence(content: str) -> str:
    """Quita un bloque de código Markdown que envuelva el JSON, si lo hay."""
    match = FENCE.match(content)
    return match.group("body") if match else content


def _parse[T: CitesNumbers](content: str, schema: type[T]) -> T | None:
    """Salida validada contra el esquema, o `None` si el JSON o el esquema fallan."""
    try:
        return schema.model_validate_json(_unfence(content))
    except (ValidationError, json.JSONDecodeError):
        return None


def _numbers_match(cited: list[float], allowed: Collection[float]) -> bool:
    """`True` si cada cifra citada es igual a alguna cifra calculada por el sistema."""
    return all(any(abs(c - a) <= NUMBER_TOLERANCE for a in allowed) for c in cited)


def _has_personal_data(texts: list[str]) -> bool:
    """`True` si algún texto tiene un teléfono, un correo o una placa."""
    return any(pattern.search(text) for text in texts for pattern in PERSONAL_DATA)


def deterministic_checks[T: CitesNumbers](
    reply: MuseReply,
    schema: type[T],
    allowed_numbers: Collection[float],
    allowed_tools: Collection[str] = ALLOWED_TOOLS,
) -> CheckResult[T]:
    """Aplica las comprobaciones deterministas a una respuesta de Muse.

    Args:
        reply: respuesta de Muse (real o grabada).
        schema: esquema Pydantic de la salida esperada.
        allowed_numbers: cifras del sistema, ya redondeadas como se citan (probabilidad
            en % entero, milímetros con 1 decimal; ADR-002 §3).
        allowed_tools: herramientas permitidas (vacía en v1).

    Returns:
        Los motivos que fallaron, en el orden de ADR-002, y la salida si pasó el esquema.
    """
    reasons: list[Reason] = []
    if reply.finish_reason != "stop":
        reasons.append(Reason.RESPUESTA_INCOMPLETA)
    parsed: T | None = None
    if reply.content is None or not reply.content.strip():
        reasons.append(Reason.RESPUESTA_VACIA)
    else:
        parsed = _parse(reply.content, schema)
        if parsed is None:
            reasons.append(Reason.ESQUEMA_INVALIDO)
        else:
            if not _numbers_match(parsed.cited_numbers(), allowed_numbers):
                reasons.append(Reason.CIFRA_NO_COINCIDE)
            if _has_personal_data(parsed.judged_claims()):
                reasons.append(Reason.DATO_PERSONAL)
    if any(tool not in allowed_tools for tool in reply.tool_calls):
        reasons.append(Reason.HERRAMIENTA_NO_PERMITIDA)
    return CheckResult(tuple(reasons), parsed if not reasons else None)
