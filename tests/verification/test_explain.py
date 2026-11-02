"""Tests de la explicación verificada del pronóstico (TASK-022, ADR-002 §2 y §3)."""

import json
import re
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from climapp.api.schemas import Forecast
from climapp.config import Settings
from climapp.verification.explain import (
    _request,
    build_explainer,
    explain_forecast,
    forecast_figures,
)
from climapp.verification.muse import (
    MuseError,
    MuseReply,
    MuseTask,
    load_recordings,
    prompt_version,
    request_hash,
)
from climapp.verification.prompts import judge_messages
from climapp.verification.schemas import ForecastExplanation
from tests.conftest import ROOT, env_example_items, rewrite_env
from tests.verification.fakes import ScriptedMuse, reply

FORECAST = Forecast(
    issued_at=datetime(2025, 1, 1, 5, 0, tzinfo=UTC),
    target_date=date(2025, 1, 1),
    prob_ge_threshold=0.14942528735632185,
    threshold_mm=20.0,
    target_rule="basin_mean",
    accum_3d_mm=40.8,
    accum_3d_level="normal",
    data_plan="plan_b_earthdata",
    variant="operativa",
    model_version="c839469b8df2",
    explanation=None,
    explanation_fallback=False,
    inputs_available=["EST-A", "EST-B"],
    stale=True,
    replay=True,
    disclaimer="No es una alerta oficial.",
    official_channels_url="",
)
TEXT = "Hay un 15 % de probabilidad de 20 mm o más mañana; en tres días se acumularon 40,8 mm."


def _explanation(text: str = TEXT, cited: list[float] | None = None) -> str:
    return json.dumps({"text": text, "numbers_cited": cited or [15, 20, 40.8]}, ensure_ascii=False)


def _ok_verdict(text: str = TEXT) -> str:
    return json.dumps({"claims": [{"text": text, "evidence": "datos", "supported": True}]})


def test_figures_are_rounded_as_the_gate_compares_them() -> None:
    assert forecast_figures(FORECAST) == {
        "probabilidad_pct": 15,
        "umbral_mm": 20.0,
        "acumulado_3d_mm": 40.8,
    }


CONTEXT = FORECAST.model_copy(
    update={
        "accum_3d_percentile": 85,
        "climatology_prob": 0.0806,
        "decision_threshold": 0.1316,
        "risk": "elevado",
    }
)


def test_figures_include_the_percentile_and_the_climatology_when_present() -> None:
    assert forecast_figures(CONTEXT) == {
        "probabilidad_pct": 15,
        "umbral_mm": 20.0,
        "acumulado_3d_mm": 40.8,
        "percentil_acumulado_pct": 85,
        "climatologia_pct": 8,
    }


def test_muse_gets_the_context_in_es_co_with_its_meaning() -> None:
    evidence = _request(CONTEXT).evidence
    for phrase in ('"valor": "15"', '"valor": "20"', '"valor": "85"', '"valor": "8"'):
        assert phrase in evidence, phrase
    assert "riesgo elevado" in evidence and "lo normal para esta época" in evidence
    assert "riesgo elevado" in _request(CONTEXT).messages[-1]["content"]  # mismo contexto


def test_explanation_with_comma_decimals_passes_the_numeric_check() -> None:
    text = "Hay un 15 % de probabilidad de 20 mm o más; en tres días se acumularon 40,8 mm."
    muse = ScriptedMuse(
        {MuseTask.EXPLAIN: [reply(_explanation(text))], MuseTask.JUDGE: [reply(_ok_verdict(text))]}
    )
    out = explain_forecast(muse, FORECAST, max_attempts=1)
    assert out is not None and "40,8" in out.text


def test_figures_without_accumulation_omit_it() -> None:
    assert "acumulado_3d_mm" not in forecast_figures(
        FORECAST.model_copy(update={"accum_3d_mm": None})
    )


def test_verified_explanation_is_returned_with_its_fallback_flag() -> None:
    muse = ScriptedMuse(
        {MuseTask.EXPLAIN: [reply(_explanation())], MuseTask.JUDGE: [reply(_ok_verdict())]}
    )
    result = explain_forecast(muse, FORECAST, max_attempts=3)
    assert result is not None
    assert (result.text, result.fallback) == (TEXT, False)
    prompt = muse.requests[0][1][-1]["content"]
    assert '"valor": "15"' in prompt and '"valor": "40,8"' in prompt  # es-CO


def test_altered_figure_is_rejected_and_explanation_is_null() -> None:
    altered = TEXT.replace("15 %", "16 %")
    muse = ScriptedMuse({MuseTask.EXPLAIN: [reply(_explanation(altered, [16, 20, 40.8]))] * 3})
    assert explain_forecast(muse, FORECAST, max_attempts=3) is None
    assert [task for task, _ in muse.requests] == [MuseTask.EXPLAIN] * 3  # el juez no corre


def test_unsupported_explanation_is_null() -> None:
    bad = json.dumps({"claims": [{"text": TEXT, "evidence": "ninguna", "supported": False}]})
    muse = ScriptedMuse({MuseTask.EXPLAIN: [reply(_explanation())], MuseTask.JUDGE: [reply(bad)]})
    assert explain_forecast(muse, FORECAST, max_attempts=1) is None


def test_muse_failure_gives_null_explanation() -> None:
    class Down:
        def complete(self, task: MuseTask, messages: object) -> object:
            raise MuseError("sin red")

    assert explain_forecast(Down(), FORECAST, max_attempts=3) is None  # type: ignore[arg-type]


def _recorded(tmp_path: Path, forecast: Forecast, explanation: str, verdict: str) -> Path:
    """Grabación exacta del explicador y del juez para `forecast`."""
    request = _request(forecast)
    judge = judge_messages([TEXT], request.evidence)
    entries = [
        (MuseTask.EXPLAIN, list(request.messages), explanation),
        (MuseTask.JUDGE, judge, verdict),
    ]
    recs = [
        {
            "task": task.value,
            "prompt_version": prompt_version(msgs),
            "request_hash": request_hash(task, msgs),
            "model": "m",
            "recorded_at": "2026-10-31T12:00:00-05:00",
            "content": content,
            "finish_reason": "stop",
            "tool_calls": [],
            "tokens_in": 1,
            "tokens_out": 2,
            "latency_ms": 3,
        }
        for task, msgs, content in entries
    ]
    path = tmp_path / "rec.json"
    path.write_text(json.dumps({"recordings": recs}, ensure_ascii=False), encoding="utf-8")
    return path


def test_demo_explainer_uses_recordings_once_per_emission(env_file: Path, tmp_path: Path) -> None:
    rec = _recorded(tmp_path, FORECAST, _explanation(), _ok_verdict())
    rewrite_env(env_file, DEMO_FALLBACK="1", MUSE_FALLBACK_FILE=str(rec))
    explainer = build_explainer(Settings(_env_file=env_file))
    assert explainer is not None
    first = explainer(FORECAST)
    assert first is not None and (first.text, first.fallback) == (TEXT, True)
    rec.unlink()  # la segunda vez sale de la memoria, sin volver a leer las grabaciones
    assert explainer(FORECAST) == first


def test_demo_explainer_without_recordings_gives_null(env_file: Path, tmp_path: Path) -> None:
    rewrite_env(env_file, DEMO_FALLBACK="1", MUSE_FALLBACK_FILE=str(tmp_path / "no.json"))
    explainer = build_explainer(Settings(_env_file=env_file))
    assert explainer is not None and explainer(FORECAST) is None


# --- evidencia del juez con el significado de cada cifra (decisión 2026-10-31) -------

E1 = FORECAST.model_copy(
    update={"prob_ge_threshold": 0.1324200913242009, "variant": "historica", "replay": True}
)
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "muse"
ALERT_TEXT = (
    "Alerta de creciente: hay un 13 % de probabilidad de 20 mm o más; "
    "en tres días cayeron 40,8 mm. No es una alerta oficial."
)


def test_judge_evidence_states_what_each_figure_means() -> None:
    evidence = _request(E1).evidence
    for phrase in (
        "mañana",
        "cuenca del río Pance",
        "basin_mean",
        "últimos tres días",
        "histórica",
        "reproducción",
        "No es una alerta oficial",
    ):
        assert phrase in evidence, phrase
    assert '"valor": "13"' in evidence and '"valor": "40,8"' in evidence  # es-CO
    assert "40.8" not in evidence and "nivel normal" not in evidence


def test_explainer_receives_the_same_meanings_as_the_judge() -> None:
    user = _request(E1).messages[-1]["content"]
    assert "basin_mean" in user and "últimos tres días" in user


def test_explainer_is_told_not_to_talk_about_floods_or_alerts() -> None:
    system = _request(E1).messages[0]["content"]
    assert "crecientes" in system and "alertas" in system


def test_changed_figure_is_still_rejected_with_the_new_evidence() -> None:
    changed = _explanation(TEXT.replace("15 %", "13 %"), [13, 20, 40.8])
    muse = ScriptedMuse({MuseTask.EXPLAIN: [reply(changed)]})
    assert explain_forecast(muse, FORECAST, max_attempts=1) is None  # FORECAST da 15 %


def test_flood_alert_explanation_is_rejected_by_the_real_judge() -> None:
    """Veredicto real de Muse (grabado el 2026-10-31) ante una explicación incorrecta."""
    (verdict,) = _historic(FIXTURES / "juez_rechaza_alerta.json")
    probe = ScriptedMuse(
        {
            MuseTask.EXPLAIN: [reply(_explanation(ALERT_TEXT, [13, 20, 40.8]))],
            MuseTask.JUDGE: [verdict],
        }
    )
    assert explain_forecast(probe, E1, max_attempts=1) is None


def test_first_real_run_is_blocked_by_the_gate() -> None:
    """Ejemplo para el video: la corrida real del 2026-10-31 que el juez rechazó 3 veces."""
    replies = _historic(FIXTURES / "e1_rechazada_2026-10-31.json")
    sequence = ScriptedMuse({MuseTask.EXPLAIN: replies[0::2], MuseTask.JUDGE: replies[1::2]})
    assert explain_forecast(sequence, E1, max_attempts=3) is None
    assert len(sequence.requests) == 6  # las 6 respuestas reales, en orden


def _historic(path: Path) -> list[MuseReply]:
    """Respuestas reales de una grabación histórica, en el orden en que llegaron.

    Son evidencia para el video, no fallback: no pasan por la búsqueda exacta.
    """
    entries = json.loads(path.read_text(encoding="utf-8"))["recordings"]
    return [reply(e["content"], e["finish_reason"]) for e in entries]


def test_fallback_without_a_recording_for_this_forecast_gives_null(
    env_file: Path, tmp_path: Path
) -> None:
    rec = tmp_path / "rec.json"
    rec.write_text(json.dumps({"recordings": []}), encoding="utf-8")
    rewrite_env(env_file, DEMO_FALLBACK="1", MUSE_FALLBACK_FILE=str(rec))
    explainer = build_explainer(Settings(_env_file=env_file))
    assert explainer is not None and explainer(FORECAST) is None


# --- la probabilidad se escribe con "%" (decisión 2026-10-31) -----------------------


def test_explainer_is_told_to_write_the_probability_with_percent_sign() -> None:
    system = _request(E1).messages[0]["content"]
    assert "%" in system and "probabilidad" in system


def test_recorded_demo_explanation_writes_the_probability_with_percent_sign() -> None:
    recordings = load_recordings(ROOT / env_example_items()["MUSE_FALLBACK_FILE"])
    explained = [r for r in recordings if r.task is MuseTask.EXPLAIN]
    text = ForecastExplanation.model_validate_json(explained[-1].content or "").text
    assert re.search(r"\b15\s?%", text), text  # operativa de la emisión 2026-10-01


def test_numbers_cited_as_es_co_text_are_parsed_as_numbers() -> None:
    """Corrida real 6 (2026-11-01): Muse devolvió "93,7" como texto al recibir cifras es-CO."""
    parsed = ForecastExplanation.model_validate_json(
        json.dumps({"text": "Hay 15 % y 93,7 mm.", "numbers_cited": ["15", "93,7", 20]})
    )
    assert parsed.numbers_cited == [15.0, 93.7, 20.0]


def test_a_cited_text_that_is_not_a_number_is_still_invalid() -> None:
    with pytest.raises(ValidationError):
        ForecastExplanation.model_validate_json(
            json.dumps({"text": "Hay 15 %.", "numbers_cited": ["quince"]})
        )


def test_real_run_6_explanations_now_pass_the_schema() -> None:
    """Las 3 respuestas reales de la corrida 6 (evidencia): con el arreglo, son válidas."""
    entries = json.loads((FIXTURES / "explicacion_cifras_texto_2026-11-01.json").read_text())
    for entry in entries["recordings"]:
        parsed = ForecastExplanation.model_validate_json(entry["content"])
        assert 93.7 in parsed.numbers_cited and "93,7" in parsed.text


# --- revisión de Muse del día 3c ------------------------------------------------------


def test_climatology_meaning_uses_the_configured_threshold() -> None:
    ten = CONTEXT.model_copy(update={"threshold_mm": 10.0})
    evidence = _request(ten).evidence
    assert "días con 10 mm o más" in evidence and "20 mm" not in evidence


def test_cached_explainer_asks_again_when_the_figures_change(
    env_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[float] = []

    def fake(_: object, forecast: Forecast, __: int) -> VerifiedExplanation:
        calls.append(forecast.prob_ge_threshold)
        return VerifiedExplanation(text="ok", fallback=True)

    monkeypatch.setattr("climapp.verification.explain.explain_forecast", fake)
    monkeypatch.setattr("climapp.verification.explain.build_client", lambda _: object())
    rewrite_env(env_file, DEMO_FALLBACK="1")
    explainer = build_explainer(Settings(_env_file=env_file))
    assert explainer is not None
    explainer(FORECAST)
    explainer(FORECAST)  # mismas cifras: desde la caché
    explainer(FORECAST.model_copy(update={"prob_ge_threshold": 0.2}))
    assert calls == [FORECAST.prob_ge_threshold, 0.2]
