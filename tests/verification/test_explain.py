"""Tests de la explicación verificada del pronóstico (TASK-022, ADR-002 §2 y §3)."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

from climapp.api.schemas import Forecast
from climapp.config import Settings
from climapp.verification.explain import build_explainer, explain_forecast, forecast_figures
from climapp.verification.muse import MuseError, MuseTask
from tests.conftest import rewrite_env
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
    assert '"probabilidad_pct": 15' in prompt and '"acumulado_3d_mm": 40.8' in prompt


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


def _recorded(tmp_path: Path, *entries: tuple[str, str]) -> Path:
    path = tmp_path / "rec.json"
    recs = [
        {
            "task": task,
            "key": None,
            "model": "m",
            "recorded_at": "2026-10-31T12:00:00-05:00",
            "content": content,
            "finish_reason": "stop",
            "tool_calls": [],
            "tokens_in": 1,
            "tokens_out": 2,
            "latency_ms": 3,
        }
        for task, content in entries
    ]
    path.write_text(json.dumps({"recordings": recs}, ensure_ascii=False), encoding="utf-8")
    return path


def test_demo_explainer_uses_recordings_once_per_emission(env_file: Path, tmp_path: Path) -> None:
    rec = _recorded(tmp_path, ("explicar", _explanation()), ("juez", _ok_verdict()))
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
