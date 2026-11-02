"""Tests de la puntuación del set de evaluación de reportes (TASK-021 paso 3, TASK-036).

El módulo vive en `eval-harness/` (no es parte de la app), así que se carga por ruta.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("scoring", ROOT / "eval-harness" / "scoring.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["scoring"] = module
    spec.loader.exec_module(module)
    return module


sc = _load()
BANDS = sc.Bands(high=0.7, low=0.3)
PRICES = sc.Prices(input_per_m=1.25, output_per_m=4.25)


def _attempt(passed: bool, tokens_out: int = 1000, latency_ms: int = 5000) -> dict[str, object]:
    return {
        "n": 1,
        "passed": passed,
        "reasons": [] if passed else ["afirmacion_sin_evidencia"],
        "tokens_in": 200,
        "tokens_out": tokens_out,
        "latency_ms": latency_ms,
    }


def _result(
    label: str, status: str, score: float | None, attempts: list[bool]
) -> dict[str, object]:
    return {
        "id": "R01",
        "clase": {"verdadero": "coherente"}.get(label, label),
        "etiqueta_esperada": label,
        "status": status,
        "confidence": score,
        "attempts": [_attempt(p) for p in attempts],
    }


@pytest.mark.parametrize(
    ("status", "score", "expected"),
    [
        ("verificado", 0.7, "coincide"),
        ("verificado", 0.5, "parcial"),
        ("verificado", 0.29, "no_coincide"),
        ("requiere_revision_humana", None, "revision_humana"),
    ],
)
def test_category_uses_the_agreement_bands(status: str, score: float | None, expected: str) -> None:
    assert sc.category(status, score, BANDS) == expected


@pytest.mark.parametrize(
    ("label", "cat", "hit"),
    [
        ("verdadero", "coincide", True),
        ("verdadero", "parcial", False),
        ("verdadero", "revision_humana", False),
        ("exagerado", "revision_humana", True),
        ("exagerado", "coincide", False),
        ("falso", "revision_humana", True),
        ("falso", "no_coincide", True),
        ("falso", "parcial", False),
    ],
)
def test_hit_follows_the_readme_rule(label: str, cat: str, hit: bool) -> None:
    assert sc.is_hit(label, cat) is hit


def test_first_attempt_category_is_review_when_attempt_one_failed() -> None:
    passed_late = _result("verdadero", "verificado", 1.0, [False, True])
    passed_first = _result("verdadero", "verificado", 1.0, [True])
    assert sc.first_attempt_category(passed_late, BANDS) == "revision_humana"
    assert sc.first_attempt_category(passed_first, BANDS) == "coincide"


def test_first_attempt_category_without_attempts_is_review() -> None:
    no_attempts = _result("verdadero", "requiere_revision_humana", None, [])
    assert sc.first_attempt_category(no_attempts, BANDS) == "revision_humana"


def test_cost_uses_prices_per_million() -> None:
    result = _result("verdadero", "verificado", 1.0, [True])
    assert sc.cost_usd(result, PRICES) == pytest.approx(200 * 1.25e-6 + 1000 * 4.25e-6)


def test_summary_by_label() -> None:
    results = [
        _result("verdadero", "verificado", 1.0, [True]),
        _result("verdadero", "verificado", 1.0, [False, True]),
        _result("verdadero", "requiere_revision_humana", None, [False, False, False]),
        _result("falso", "verificado", 0.0, [True]),
    ]
    summary = sc.summarize(results, BANDS, PRICES)
    true = summary["por_etiqueta"]["verdadero"]
    assert true["n"] == 3
    assert true["pass_at_1"] == pytest.approx(1 / 3)
    assert true["acierto_en_3"] == pytest.approx(2 / 3)
    assert true["revision_humana"] == pytest.approx(1 / 3)
    assert summary["matriz"]["verdadero"] == {
        "coincide": 2,
        "parcial": 0,
        "no_coincide": 0,
        "revision_humana": 1,
    }
    assert summary["total"]["n"] == 4
    assert summary["total"]["acierto_en_3"] == pytest.approx(3 / 4)
    assert summary["total"]["costo_usd"] == pytest.approx(
        sum(sc.cost_usd(r, PRICES) for r in results)
    )


def test_summary_latency_is_per_report_sum_of_attempts() -> None:
    results = [_result("falso", "verificado", 0.0, [True, True])]
    summary = sc.summarize(results, BANDS, PRICES)
    assert summary["total"]["latencia_p50_s"] == pytest.approx(10.0)


def test_summary_by_class_separates_hard_rows() -> None:
    hard = _result("verdadero", "requiere_revision_humana", None, [False] * 3) | {
        "clase": "dificil"
    }
    summary = sc.summarize([hard], BANDS, PRICES)
    assert summary["por_clase"]["dificil"]["revision_humana"] == 1.0


def test_estimate_scales_observed_cost() -> None:
    est = sc.estimate_usd(observed_usd=1.0, runs=4, factor=1.5)
    assert est == pytest.approx(6.0)
