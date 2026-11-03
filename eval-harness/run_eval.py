"""Corre el set de evaluación de reportes con Muse real (TASK-021 paso 3, TASK-036).

Cada reporte de `reportes_simulados.jsonl` pasa por el mismo `ReportVerifier` de la app
(compuerta, juez, reintentos y confianza), con `received_at` igual a su fecha y hora
local. Guarda un resultado por reporte y el resumen de `scoring.summarize`.

Uso:
    uv run python eval-harness/run_eval.py --run base --effort-structure low --effort-judge medium

Llama a la API real (cuesta dinero): `DEMO_FALLBACK` debe ser 0.
"""

import argparse
import json
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from scoring import Bands, Prices, mark_retry, needs_api_retry, summarize

from climapp.api.reports import _verifier
from climapp.api.schemas import ReportRecord
from climapp.config import Settings
from climapp.logging import configure_logging, get_logger
from climapp.verification.muse import build_client

log = get_logger(__name__)
EFFORTS = ("low", "medium", "high")


class RunSettings(BaseSettings):
    """Entradas, salidas y precios de la evaluación (prefijo `EVAL_`).

    Attributes:
        reports: reportes simulados, relativos a la raíz del repositorio.
        results_dir: carpeta de resultados.
        price_in_per_m: US$ por millón de tokens de entrada (ADR-002).
        price_out_per_m: US$ por millón de tokens de salida (ADR-002).
        workers: reportes en paralelo.
    """

    model_config = SettingsConfigDict(
        env_prefix="EVAL_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    reports: Path
    results_dir: Path
    price_in_per_m: float = Field(gt=0)
    price_out_per_m: float = Field(gt=0)
    workers: int = Field(ge=1)


def _record(row: dict[str, object], settings: Settings) -> ReportRecord:
    """Reporte nuevo con el texto simulado, recibido en su fecha y hora local."""
    local = datetime.fromisoformat(f"{row['fecha']}T{row['hora_local']}")
    return ReportRecord(
        id=uuid4(),
        received_at=local.replace(tzinfo=settings.local_timezone),
        lat=settings.demo_example_lat,
        lon=settings.demo_example_lon,
        status="verificando",
        reject_reason=None,
        structured=None,
        confidence=None,
        attempts=[],
        fallback=False,
        text=str(row["texto"]),
        photo_file=None,
    )


def _result(
    row: dict[str, object], record: ReportRecord, efforts: Sequence[str]
) -> dict[str, object]:
    """Resultado de un reporte: lo esperado, lo obtenido y sus intentos."""
    out = record.model_dump(
        mode="json", include={"status", "review_reason", "structured", "attempts"}
    )
    conf = record.confidence
    return {
        "id": row["id"],
        "clase": row["clase"],
        "etiqueta_esperada": row["etiqueta_esperada"],
        "effort_structure": efforts[0],
        "effort_judge": efforts[1],
        **out,
        "confidence": None if conf is None else conf.score,
        "confidence_sources": None if conf is None else conf.model_dump(mode="json")["sources"],
    }


def run(
    settings: Settings, cfg: RunSettings, efforts: Sequence[str], limit: int | None
) -> list[dict[str, object]]:
    """Verifica todos los reportes con los esfuerzos dados.

    Raises:
        RuntimeError: si `DEMO_FALLBACK` está activo (la evaluación es con Muse real).
    """
    if settings.demo_fallback:
        msg = "DEMO_FALLBACK=1: la evaluación exige Muse real"
        raise RuntimeError(msg)
    tuned = settings.model_copy(
        update={"muse_effort_structure": efforts[0], "muse_effort_judge": efforts[1]}
    )
    verifier = _verifier(tuned, build_client(tuned))
    rows = [json.loads(line) for line in cfg.reports.read_text(encoding="utf-8").splitlines()]
    rows = rows[:limit] if limit else rows

    def one(row: dict[str, object]) -> dict[str, object]:
        result = _result(row, verifier.verify(_record(row, tuned)), efforts)
        log.info("eval.report_done", report_id=row["id"], status=result["status"])
        return result

    with ThreadPoolExecutor(max_workers=cfg.workers) as pool:
        results = list(pool.map(one, rows))
    return _retry_api_failures(rows, results, one)


def _retry_api_failures(
    rows: Sequence[dict[str, object]],
    results: list[dict[str, object]],
    one: Callable[[dict[str, object]], dict[str, object]],
) -> list[dict[str, object]]:
    """Reintenta una vez, aparte y en serie, los reportes que cayeron por la API."""
    merged = []
    for row, first in zip(rows, results, strict=True):
        if needs_api_retry(first):
            log.warning("eval.api_retry", report_id=row["id"])
            merged.append(mark_retry(first, one(row)))
        else:
            merged.append(first)
    return merged


def _write(
    name: str, results: list[dict[str, object]], settings: Settings, cfg: RunSettings
) -> Path:
    """Escribe los resultados (JSONL) y el resumen (JSON) de la corrida."""
    cfg.results_dir.mkdir(parents=True, exist_ok=True)
    lines = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in results)
    (cfg.results_dir / f"{name}.jsonl").write_text(lines, encoding="utf-8")
    bands = Bands(settings.agreement_high, settings.agreement_low)
    summary = summarize(results, bands, Prices(cfg.price_in_per_m, cfg.price_out_per_m))
    path = cfg.results_dir / f"{name}.summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> None:
    """CLI: `--run`, `--effort-structure`, `--effort-judge` y `--limit`."""
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="nombre de la corrida")
    parser.add_argument("--effort-structure", choices=EFFORTS, required=True)
    parser.add_argument("--effort-judge", choices=EFFORTS, required=True)
    parser.add_argument("--limit", type=int, default=None, help="solo los primeros N reportes")
    args = parser.parse_args()
    settings, cfg = Settings(), RunSettings()
    efforts = (args.effort_structure, args.effort_judge)
    results = run(settings, cfg, efforts, args.limit)
    path = _write(args.run, results, settings, cfg)
    log.info("eval.run_done", run=args.run, reports=len(results), summary=str(path))


if __name__ == "__main__":
    main()
