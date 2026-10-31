"""Tests de las comprobaciones deterministas de la compuerta (TASK-012, ADR-002 §3.1)."""

import json

import pytest

from climapp.verification.checks import Reason, deterministic_checks
from climapp.verification.schemas import ForecastExplanation, ReportStructured
from tests.verification.fakes import reply

REPORT = {
    "event_type": "lluvia",
    "intensity": "fuerte",
    "observed_at": "2024-12-31T16:30:00-05:00",
    "claims": ["llueve fuerte en la parte alta"],
    "numbers_cited": [],
}
EXPLANATION = {
    "text": "La probabilidad de 20 mm o más mañana es 15 %; el acumulado de 3 días es 40,8 mm.",
    "numbers_cited": [15, 40.8, 20],
}
ALLOWED = {15.0, 40.8, 20.0}


def _report(**change: object) -> str:
    return json.dumps(REPORT | change)


def _explanation(**change: object) -> str:
    return json.dumps(EXPLANATION | change, ensure_ascii=False)


def test_valid_report_passes_and_is_parsed() -> None:
    result = deterministic_checks(reply(_report()), ReportStructured, ALLOWED)
    assert result.passed
    assert result.reasons == ()
    assert isinstance(result.parsed, ReportStructured)
    assert result.parsed.claims == ["llueve fuerte en la parte alta"]


def test_valid_explanation_passes() -> None:
    result = deterministic_checks(reply(_explanation()), ForecastExplanation, ALLOWED)
    assert result.passed


def test_unfinished_response_is_respuesta_incompleta() -> None:
    result = deterministic_checks(reply(_report(), "length"), ReportStructured, ALLOWED)
    assert result.reasons == (Reason.RESPUESTA_INCOMPLETA,)
    assert result.parsed is None


@pytest.mark.parametrize("content", [None, "", "   \n"])
def test_empty_content_is_respuesta_vacia(content: str | None) -> None:
    result = deterministic_checks(reply(content), ReportStructured, ALLOWED)
    assert result.reasons == (Reason.RESPUESTA_VACIA,)


@pytest.mark.parametrize(
    "content",
    [
        "no es json",
        _report(event_type="tornado"),
        _report(claims="una sola"),
        _report(extra="campo inventado"),
        json.dumps({k: v for k, v in REPORT.items() if k != "observed_at"}),
        _explanation(text="x" * 601),
    ],
)
def test_invalid_schema_is_esquema_invalido(content: str) -> None:
    schema = ForecastExplanation if "text" in content else ReportStructured
    result = deterministic_checks(reply(content), schema, ALLOWED)
    assert result.reasons == (Reason.ESQUEMA_INVALIDO,)


def test_json_inside_a_code_fence_is_accepted() -> None:
    fenced = f"```json\n{_report()}\n```"
    assert deterministic_checks(reply(fenced), ReportStructured, ALLOWED).passed


def test_cited_number_that_differs_is_cifra_no_coincide() -> None:
    result = deterministic_checks(reply(_report(numbers_cited=[16])), ReportStructured, ALLOWED)
    assert result.reasons == (Reason.CIFRA_NO_COINCIDE,)


def test_number_in_the_text_that_differs_is_cifra_no_coincide() -> None:
    text = "La probabilidad es 15 %; el acumulado de 3 días es 41 mm."
    content = _explanation(text=text, numbers_cited=[15])
    result = deterministic_checks(reply(content), ForecastExplanation, ALLOWED | {3.0})
    assert result.reasons == (Reason.CIFRA_NO_COINCIDE,)


def test_decimal_comma_in_the_text_is_read_as_a_number() -> None:
    content = _explanation(text="Acumulado: 40,8 mm.", numbers_cited=[])
    assert deterministic_checks(reply(content), ForecastExplanation, {40.8}).passed


def test_any_tool_call_is_herramienta_no_permitida() -> None:
    result = deterministic_checks(
        reply(_report(), tool_calls=("buscar_web",)), ReportStructured, ALLOWED
    )
    assert result.reasons == (Reason.HERRAMIENTA_NO_PERMITIDA,)


def test_all_failing_reasons_are_reported_in_adr_order() -> None:
    content = _report(numbers_cited=[99])
    result = deterministic_checks(
        reply(content, "tool_calls", tool_calls=("x",)), ReportStructured, ALLOWED
    )
    assert result.reasons == (
        Reason.RESPUESTA_INCOMPLETA,
        Reason.CIFRA_NO_COINCIDE,
        Reason.HERRAMIENTA_NO_PERMITIDA,
    )


def test_empty_content_skips_schema_and_numbers_but_not_tools() -> None:
    result = deterministic_checks(
        reply(None, "length", tool_calls=("x",)), ReportStructured, ALLOWED
    )
    assert result.reasons == (
        Reason.RESPUESTA_INCOMPLETA,
        Reason.RESPUESTA_VACIA,
        Reason.HERRAMIENTA_NO_PERMITIDA,
    )


def test_reason_values_match_the_data_model() -> None:
    assert [r.value for r in Reason] == [
        "respuesta_incompleta",
        "respuesta_vacia",
        "esquema_invalido",
        "cifra_no_coincide",
        "herramienta_no_permitida",
        "afirmacion_sin_evidencia",
    ]
