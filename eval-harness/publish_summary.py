"""Junta los resúmenes de las corridas en `REPORT_EVAL_FILE` para `GET /evaluation` (TASK-036).

Uso:
    uv run python eval-harness/publish_summary.py --run base_low-medium:low:medium [--run ...]
"""

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from climapp.config import Settings
from climapp.logging import configure_logging, get_logger

log = get_logger(__name__)
KEYS = {
    "n": "n",
    "pass_at_1": "pass_at_1",
    "acierto_en_3": "within_3",
    "revision_humana": "human_review",
    "intentos_medios": "mean_attempts",
    "costo_usd": "cost_usd",
    "latencia_p50_s": "latency_p50_s",
    "latencia_p95_s": "latency_p95_s",
}
LABELS_FROM = "datos: regla escrita en eval-harness/README.md (SP-10, SP-17), sin LLM"
TEXTS_FROM = "LLM (opencode) a partir de una especificación derivada de los datos"

Summary = Mapping[str, Mapping[str, object]]


class PublishSettings(BaseSettings):
    """Carpeta de resultados de `run_eval.py` (`EVAL_RESULTS_DIR`)."""

    model_config = SettingsConfigDict(
        env_prefix="EVAL_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    results_dir: Path


def _rates(rates: Mapping[str, object]) -> dict[str, object]:
    """Tasas con las claves del contrato (`ReportEvalRates`)."""
    return {KEYS[k]: v for k, v in rates.items() if k in KEYS}


def _by(groups: Mapping[str, object]) -> dict[str, object]:
    """Tasas por grupo con las claves del contrato."""
    return {name: _rates(rates) for name, rates in groups.items() if isinstance(rates, Mapping)}


def run_entry(
    run: str, effort_structure: str, effort_judge: str, summary: Summary
) -> dict[str, object]:
    """Una corrida en el formato `ReportEvalRun`.

    Args:
        run: nombre de la corrida.
        effort_structure: esfuerzo de la estructuración.
        effort_judge: esfuerzo del juez.
        summary: salida de `scoring.summarize`.

    Returns:
        La corrida con las claves del contrato.
    """
    return {
        "run": run,
        "effort_structure": effort_structure,
        "effort_judge": effort_judge,
        "total": _rates(summary["total"]),
        "by_label": _by(summary["por_etiqueta"]),
        "by_class": _by(summary["por_clase"]),
        "matrix": dict(summary["matriz"]),
    }


def publish(
    results_dir: Path,
    runs: Sequence[tuple[str, str, str]],
    out: Path,
    *,
    model: str,
    evaluated_on: str,
) -> Path:
    """Escribe `out` con las corridas pedidas, leídas de `<results_dir>/<run>.summary.json`.

    Raises:
        OSError, json.JSONDecodeError: si falta o está corrupto un resumen.
    """
    entries = []
    for run, structure, judge in runs:
        summary = json.loads((results_dir / f"{run}.summary.json").read_text(encoding="utf-8"))
        entries.append(run_entry(run, structure, judge, summary))
    body = {
        "model": model,
        "evaluated_on": evaluated_on,
        "reports": entries[0]["total"]["n"],  # type: ignore[index]
        "labels_from": LABELS_FROM,
        "texts_from": TEXTS_FROM,
        "runs": entries,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def main() -> None:
    """CLI: `--run nombre:esfuerzo_estructura:esfuerzo_juez` (repetible) y `--date`."""
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", required=True)
    parser.add_argument("--date", required=True, help="fecha de la evaluación (AAAA-MM-DD)")
    args = parser.parse_args()
    settings, cfg = Settings(), PublishSettings()
    runs = [tuple(r.split(":")) for r in args.run]
    path = publish(
        cfg.results_dir,
        runs,
        settings.report_eval_file,
        model=settings.muse_model,
        evaluated_on=args.date,
    )
    log.info("eval.summary_published", path=str(path), runs=len(runs))


if __name__ == "__main__":
    main()
