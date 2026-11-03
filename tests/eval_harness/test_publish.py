"""Tests del publicador del resumen de la evaluación de reportes (TASK-036)."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

from climapp.api.schemas import ReportVerificationEval

ROOT = Path(__file__).resolve().parents[2]


def _load() -> ModuleType:
    path = ROOT / "eval-harness" / "publish_summary.py"
    spec = importlib.util.spec_from_file_location("publish_summary", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["publish_summary"] = module
    spec.loader.exec_module(module)
    return module


pub = _load()
RATES_ES = {
    "n": 5,
    "pass_at_1": 0.2,
    "acierto_en_3": 0.4,
    "revision_humana": 0.6,
    "intentos_medios": 2.4,
    "costo_usd": 0.2,
    "latencia_p50_s": 60.0,
    "latencia_p95_s": 80.0,
}
SUMMARY = {
    "total": RATES_ES,
    "por_etiqueta": {"verdadero": RATES_ES},
    "por_clase": {"dificil": RATES_ES},
    "matriz": {"verdadero": {"coincide": 2, "parcial": 0, "no_coincide": 0, "revision_humana": 3}},
}


def test_run_entry_uses_contract_keys() -> None:
    entry = pub.run_entry("base_low-medium", "low", "medium", SUMMARY)
    assert entry["total"]["within_3"] == 0.4
    assert entry["total"]["human_review"] == 0.6
    assert entry["by_class"]["dificil"]["mean_attempts"] == 2.4
    assert entry["matrix"] == SUMMARY["matriz"]


def test_publish_writes_a_file_valid_for_the_api(tmp_path: Path) -> None:
    (tmp_path / "base_low-medium.summary.json").write_text(json.dumps(SUMMARY), encoding="utf-8")
    out = tmp_path / "report_eval.json"
    runs = [("base_low-medium", "low", "medium")]
    pub.publish(tmp_path, runs, out, model="muse-spark-1.3", evaluated_on="2026-11-02")
    parsed = ReportVerificationEval.model_validate_json(out.read_text(encoding="utf-8"))
    assert parsed.reports == 5
    assert parsed.runs[0].effort_judge == "medium"


def test_run_spec_must_have_name_and_two_efforts() -> None:
    assert pub.parse_run("base_v2:low:medium") == ("base_v2", "low", "medium")
    for bad in ("base_v2", "base_v2:low", "a:b:c:d", "base_v2:low:extremo"):
        try:
            pub.parse_run(bad)
        except ValueError as err:
            assert "nombre:esfuerzo_estructura:esfuerzo_juez" in str(err)
        else:
            raise AssertionError(bad)


def test_texts_from_names_the_generator_model() -> None:
    assert "Muse Spark 1.3" in pub.TEXTS_FROM
