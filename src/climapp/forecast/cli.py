"""Comando reproducible que entrena, evalúa y publica pronósticos (ADR-001).

Uso: `uv run climapp-train`. Lee la tabla diaria y CHIRPS de `DATA_DIR` y escribe
`EVALUATION_FILE` y `FORECASTS_FILE`, que la API sirve sin recalcular.
"""

import hashlib
import json
from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from climapp.config import Settings
from climapp.data.chirps_reader import read_chirps_xlsx
from climapp.data.daily import file_sha256, read_daily_csv
from climapp.data.models import DailyPrecip
from climapp.forecast.dataset import Periods, build_samples
from climapp.forecast.evaluation import EvalConfig, run_evaluation
from climapp.forecast.features import chirps_daily_mean
from climapp.forecast.model import RFParams
from climapp.forecast.publish import ForecastRecord, PublishContext, forecast_records
from climapp.forecast.target import basin_days
from climapp.logging import configure_logging, get_logger

log = get_logger(__name__)
CHIRPS_INPUT = "CHIRPS"
VERSION_CHARS = 12
PLANS_PENDING = {
    "principal": "requiere IMERG Early en el modelo (TASK-009 y TASK-028)",
    "plan_b_datos": "es el plan B sin estaciones (TASK-035)",
}


def eval_config(settings: Settings) -> EvalConfig:
    """Configuración de evaluación a partir de `Settings`."""
    return EvalConfig(
        periods=Periods(
            settings.train_start, settings.train_end, settings.valid_end, settings.test_end
        ),
        rf=RFParams(
            settings.rf_n_estimators, settings.rf_min_samples_leaf, settings.rf_random_state
        ),
        window_days=settings.climatology_window_days,
        n_bins=settings.reliability_bins,
        threshold_mm=settings.forecast_threshold_mm,
        rule=settings.target_rule,
        data_plan=settings.data_plan,
    )


def _inputs(rows: Sequence[DailyPrecip], chirps: dict[date, float]) -> dict[date, list[str]]:
    """Series con dato por día: estaciones válidas y CHIRPS."""
    inputs: defaultdict[date, list[str]] = defaultdict(list)
    for row in rows:
        if row.valid and not row.imputed:
            inputs[row.date].append(row.series_id)
    for day in chirps:
        inputs[day].append(CHIRPS_INPUT)
    return {day: sorted(series) for day, series in inputs.items()}


def _model_version(sources: Sequence[Path], config: EvalConfig) -> str:
    """Hash de los archivos de entrada y de los parámetros del modelo."""
    digest = hashlib.sha256()
    for path in sources:
        digest.update(file_sha256(path).encode())
    digest.update(repr(config).encode())
    return digest.hexdigest()[:VERSION_CHARS]


def _write_json(path: Path, payload: object) -> Path:
    """Escribe JSON UTF-8, creando los directorios que falten."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def train_and_publish(settings: Settings) -> tuple[Path, Path]:
    """Entrena el RF, evalúa frente a las líneas base y publica los pronósticos.

    Returns:
        Rutas de `EVALUATION_FILE` y `FORECASTS_FILE`.

    Raises:
        ValueError: si el plan de datos todavía no está implementado o faltan datos.
        OSError: si un archivo no se puede leer o escribir.
    """
    if settings.data_plan in PLANS_PENDING:
        msg = f"DATA_PLAN={settings.data_plan} {PLANS_PENDING[settings.data_plan]}"
        raise ValueError(msg)
    daily_path = settings.data_dir / settings.daily_stations_file
    chirps_paths = [settings.data_dir / p for p in settings.chirps_files]
    rows = read_daily_csv(daily_path)
    chirps = chirps_daily_mean(v for p in chirps_paths for v in read_chirps_xlsx(p))
    config = eval_config(settings)
    imputed = {r.date for r in rows if r.imputed}
    samples = build_samples(basin_days(rows), chirps, config.threshold_mm, config.rule, imputed)
    result = run_evaluation(samples, config)
    ctx = PublishContext(
        from_issue=settings.valid_end,
        tz=settings.local_timezone,
        accum3_threshold_mm=settings.accum3_threshold_mm,
        model_version=_model_version([daily_path, *chirps_paths], config),
        inputs=_inputs(rows, chirps),
    )
    records = forecast_records(samples, result.model, ctx)
    return _publish(settings, result.report.model_dump(mode="json"), records)


def _publish(
    settings: Settings, report: dict[str, object], records: Sequence[ForecastRecord]
) -> tuple[Path, Path]:
    """Escribe los dos artefactos y registra el evento."""
    evaluation = _write_json(settings.data_dir / settings.evaluation_file, report)
    forecasts = _write_json(
        settings.data_dir / settings.forecasts_file, [r.model_dump(mode="json") for r in records]
    )
    log.info("forecast.published", forecasts=len(records), last=str(records[-1].target_date))
    return evaluation, forecasts


def main() -> None:
    """Punto de entrada de `climapp-train`."""
    configure_logging()
    train_and_publish(Settings())
