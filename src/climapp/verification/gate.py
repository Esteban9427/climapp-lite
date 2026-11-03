"""Compuerta de verificación: deterministas → juez → reintentos (ADR-002 §3).

Cada intento recibe los motivos del anterior. Tras `max_attempts` fallos el estado es
`requiere_revision_humana`. Cada intento queda registrado con sus motivos, tokens y
latencia (generador y juez sumados). La compuerta no se salta, ni en la demo.
"""

import unicodedata
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Literal

from climapp.logging import get_logger
from climapp.verification.checks import CitesNumbers, Reason, deterministic_checks
from climapp.verification.muse import Message, MuseClient, MuseReply, MuseTask
from climapp.verification.prompts import feedback_message, judge_messages
from climapp.verification.schemas import JudgeVerdict

log = get_logger(__name__)
GateStatus = Literal["verificado", "requiere_revision_humana"]


@dataclass(frozen=True, slots=True)
class GateRequest[T: CitesNumbers]:
    """Lo que se verifica.

    Attributes:
        task: tarea del generador (`estructurar` o `explicar`).
        schema: esquema de la salida.
        messages: mensajes del primer intento.
        allowed_numbers: cifras del sistema, redondeadas como se citan.
        evidence: evidencia que recibe el juez (texto del ciudadano y datos entregados).
        source_text: texto del ciudadano, para `cifra_omitida` (`None` en la explicación).
    """

    task: MuseTask
    schema: type[T]
    messages: Sequence[Message]
    allowed_numbers: Collection[float]
    evidence: str
    source_text: str | None = None


@dataclass(frozen=True, slots=True)
class VerificationAttempt:
    """Registro de un intento (`docs/data-model.md`)."""

    n: int
    passed: bool
    reasons: tuple[Reason, ...]
    finish_reason: str
    tokens_in: int
    tokens_out: int
    latency_ms: int


@dataclass(frozen=True, slots=True)
class GateResult[T]:
    """Estado final, salida verificada (o `None`) e historial de intentos."""

    status: GateStatus
    output: T | None
    attempts: tuple[VerificationAttempt, ...]
    fallback: bool


def _normalized(text: str) -> str:
    """Texto comparable: sin diferencias de mayúsculas, espacios ni forma Unicode."""
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def _judge(
    client: MuseClient, claims: Sequence[str], evidence: str
) -> tuple[tuple[Reason, ...], MuseReply]:
    """Pide el veredicto del juez y lo convierte en motivos de rechazo.

    Una afirmación que el juez no devuelve, o que marca `supported=false`, es
    `afirmacion_sin_evidencia`. Si la respuesta del juez no pasa las deterministas,
    sus motivos rechazan el intento.
    """
    reply = client.complete(MuseTask.JUDGE, judge_messages(claims, evidence))
    checked = deterministic_checks(reply, JudgeVerdict, allowed_numbers=())
    if checked.parsed is None:
        return checked.reasons, reply
    supported = {_normalized(c.text) for c in checked.parsed.claims if c.supported}
    if all(_normalized(c) in supported for c in claims):
        return (), reply
    return (Reason.AFIRMACION_SIN_EVIDENCIA,), reply


def _attempt[T: CitesNumbers](
    client: MuseClient, request: GateRequest[T], n: int, messages: Sequence[Message]
) -> tuple[VerificationAttempt, T | None, list[MuseReply]]:
    """Un intento: generador, deterministas y, si pasan, juez."""
    reply = client.complete(request.task, messages)
    replies = [reply]
    checked = deterministic_checks(
        reply, request.schema, request.allowed_numbers, source_text=request.source_text
    )
    reasons = checked.reasons
    if checked.parsed is not None:
        reasons, judge_reply = _judge(client, checked.parsed.judged_claims(), request.evidence)
        replies.append(judge_reply)
    attempt = VerificationAttempt(
        n=n,
        passed=not reasons,
        reasons=reasons,
        finish_reason=reply.finish_reason,
        tokens_in=sum(r.tokens_in for r in replies),
        tokens_out=sum(r.tokens_out for r in replies),
        latency_ms=sum(r.latency_ms for r in replies),
    )
    return attempt, (checked.parsed if not reasons else None), replies


def run_gate[T: CitesNumbers](
    client: MuseClient, request: GateRequest[T], max_attempts: int
) -> GateResult[T]:
    """Verifica una salida de Muse con hasta `max_attempts` intentos (`VERIFY_MAX_ATTEMPTS`).

    Raises:
        MuseError: si Muse no responde (el intento no se puede hacer).
    """
    attempts: list[VerificationAttempt] = []
    replies: list[MuseReply] = []
    messages = list(request.messages)
    for n in range(1, max_attempts + 1):
        attempt, output, used = _attempt(client, request, n, messages)
        attempts.append(attempt)
        replies.extend(used)
        log.info(
            "gate.attempt",
            task=request.task.value,
            n=n,
            passed=attempt.passed,
            reasons=[r.value for r in attempt.reasons],
        )
        if output is not None:
            return GateResult("verificado", output, tuple(attempts), _any_fallback(replies))
        messages = [*request.messages, feedback_message(attempt.reasons)]
    return GateResult("requiere_revision_humana", None, tuple(attempts), _any_fallback(replies))


def _any_fallback(replies: Sequence[MuseReply]) -> bool:
    """`True` si alguna respuesta usada era grabada."""
    return any(r.fallback for r in replies)
