"""Tests del juez y del bucle de reintentos de la compuerta (TASK-013, ADR-002 §3)."""

import json

from climapp.verification.checks import Reason
from climapp.verification.gate import GateRequest, run_gate
from climapp.verification.muse import MuseTask
from climapp.verification.schemas import ReportStructured
from tests.verification.fakes import ScriptedMuse, reply

CLAIMS = ["llueve fuerte en la parte alta", "el río está crecido"]
GOOD = json.dumps(
    {
        "event_type": "lluvia",
        "intensity": "fuerte",
        "observed_at": "2024-12-31T16:30:00-05:00",
        "claims": CLAIMS,
        "numbers_cited": [],
    }
)
REQUEST = GateRequest(
    task=MuseTask.STRUCTURE,
    schema=ReportStructured,
    messages=[{"role": "user", "content": "Llueve duro arriba y el río viene crecido"}],
    allowed_numbers=frozenset(),
    evidence="Texto del ciudadano: Llueve duro arriba y el río viene crecido",
)


def _verdict(*supported: bool, claims: list[str] = CLAIMS) -> str:
    return json.dumps(
        {
            "claims": [
                {"text": c, "evidence": "texto del ciudadano", "supported": s}
                for c, s in zip(claims, supported, strict=True)
            ]
        }
    )


def test_approved_on_the_first_attempt() -> None:
    muse = ScriptedMuse(
        {MuseTask.STRUCTURE: [reply(GOOD)], MuseTask.JUDGE: [reply(_verdict(True, True))]}
    )
    result = run_gate(muse, REQUEST, max_attempts=3)
    assert result.status == "verificado"
    assert isinstance(result.output, ReportStructured)
    (attempt,) = result.attempts
    assert (attempt.n, attempt.passed, attempt.reasons) == (1, True, ())
    assert (attempt.tokens_in, attempt.tokens_out) == (200, 400)  # generador + juez
    assert [task for task, _ in muse.requests] == [MuseTask.STRUCTURE, MuseTask.JUDGE]


def test_approved_on_the_third_attempt_with_the_reasons_of_each_failure() -> None:
    muse = ScriptedMuse(
        {
            MuseTask.STRUCTURE: [reply("no es json"), reply(GOOD), reply(GOOD)],
            MuseTask.JUDGE: [reply(_verdict(True, False)), reply(_verdict(True, True))],
        }
    )
    result = run_gate(muse, REQUEST, max_attempts=3)
    assert result.status == "verificado"
    assert [(a.n, a.passed, a.reasons) for a in result.attempts] == [
        (1, False, (Reason.ESQUEMA_INVALIDO,)),
        (2, False, (Reason.AFIRMACION_SIN_EVIDENCIA,)),
        (3, True, ()),
    ]


def test_three_failures_require_human_review() -> None:
    muse = ScriptedMuse({MuseTask.STRUCTURE: [reply(None), reply(None), reply(GOOD, "length")]})
    result = run_gate(muse, REQUEST, max_attempts=3)
    assert result.status == "requiere_revision_humana"
    assert result.output is None
    assert len(result.attempts) == 3
    assert result.attempts[-1].reasons == (Reason.RESPUESTA_INCOMPLETA,)
    assert result.attempts[-1].finish_reason == "length"


def test_judge_is_not_called_when_deterministic_checks_fail() -> None:
    muse = ScriptedMuse({MuseTask.STRUCTURE: [reply("{}")]})
    run_gate(muse, REQUEST, max_attempts=1)
    assert [task for task, _ in muse.requests] == [MuseTask.STRUCTURE]


def test_each_retry_receives_the_previous_reasons() -> None:
    muse = ScriptedMuse({MuseTask.STRUCTURE: [reply(None, "length"), reply(None)]})
    run_gate(muse, REQUEST, max_attempts=2)
    first, second = (msgs for task, msgs in muse.requests)
    assert first == REQUEST.messages
    feedback = second[-1]["content"]
    assert second[: len(REQUEST.messages)] == REQUEST.messages
    assert "respuesta_incompleta" in feedback and "respuesta_vacia" in feedback


def test_claim_missing_from_the_verdict_is_afirmacion_sin_evidencia() -> None:
    partial = _verdict(True, claims=CLAIMS[:1])
    muse = ScriptedMuse({MuseTask.STRUCTURE: [reply(GOOD)], MuseTask.JUDGE: [reply(partial)]})
    result = run_gate(muse, REQUEST, max_attempts=1)
    assert result.attempts[0].reasons == (Reason.AFIRMACION_SIN_EVIDENCIA,)


def test_invalid_judge_response_fails_the_attempt_with_its_reason() -> None:
    muse = ScriptedMuse(
        {MuseTask.STRUCTURE: [reply(GOOD)], MuseTask.JUDGE: [reply("sí, todo bien")]}
    )
    result = run_gate(muse, REQUEST, max_attempts=1)
    assert result.status == "requiere_revision_humana"
    assert result.attempts[0].reasons == (Reason.ESQUEMA_INVALIDO,)


def test_judge_receives_the_claims_and_the_evidence() -> None:
    muse = ScriptedMuse(
        {MuseTask.STRUCTURE: [reply(GOOD)], MuseTask.JUDGE: [reply(_verdict(True, True))]}
    )
    run_gate(muse, REQUEST, max_attempts=1)
    judge_prompt = json.dumps(muse.requests[1][1], ensure_ascii=False)
    assert all(claim in judge_prompt for claim in CLAIMS)
    assert REQUEST.evidence in judge_prompt


def test_recorded_replies_mark_the_result_as_fallback() -> None:
    muse = ScriptedMuse(
        {
            MuseTask.STRUCTURE: [reply(GOOD, fallback=True)],
            MuseTask.JUDGE: [reply(_verdict(True, True), fallback=True)],
        }
    )
    assert run_gate(muse, REQUEST, max_attempts=1).fallback is True
    live = ScriptedMuse(
        {MuseTask.STRUCTURE: [reply(GOOD)], MuseTask.JUDGE: [reply(_verdict(True, True))]}
    )
    assert run_gate(live, REQUEST, max_attempts=1).fallback is False


def test_attempt_latency_adds_generator_and_judge() -> None:
    muse = ScriptedMuse(
        {
            MuseTask.STRUCTURE: [reply(GOOD, latency_ms=700)],
            MuseTask.JUDGE: [reply(_verdict(True, True), latency_ms=900)],
        }
    )
    assert run_gate(muse, REQUEST, max_attempts=1).attempts[0].latency_ms == 1600


def test_judge_cut_by_max_tokens_is_an_incomplete_answer() -> None:
    """Juez sin contenido por el tope de tokens: `respuesta_incompleta`, nunca aprobado."""
    muse = ScriptedMuse(
        {MuseTask.STRUCTURE: [reply(GOOD)] * 3, MuseTask.JUDGE: [reply(None, "length")] * 3}
    )
    result = run_gate(muse, REQUEST, max_attempts=3)
    assert result.status == "requiere_revision_humana"
    assert all("respuesta_incompleta" in a.reasons for a in result.attempts)


def test_report_that_omits_a_quantity_is_never_verified() -> None:
    """Fallo B: "subió 5 metros" con numbers_cited vacío va a revisión humana."""
    text = "Reporte simulado: el río subió 5 metros y arrasó con las casas"
    request = GateRequest(
        task=MuseTask.STRUCTURE,
        schema=ReportStructured,
        messages=[{"role": "user", "content": text}],
        allowed_numbers=frozenset(),
        evidence=f"Texto del ciudadano: {text}",
        source_text=text,
    )
    muse = ScriptedMuse(
        {MuseTask.STRUCTURE: [reply(GOOD)] * 3, MuseTask.JUDGE: [reply(_verdict(True, True))] * 3}
    )
    result = run_gate(muse, request, max_attempts=3)
    assert result.status == "requiere_revision_humana"
    assert result.output is None
    assert all("cifra_omitida" in a.reasons for a in result.attempts)
