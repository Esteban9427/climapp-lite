"""Evidencia de un reporte para la confianza (ADR-002 §4), leída de los artefactos.

- Estaciones: tabla diaria (`DAILY_STATIONS_FILE`), días válidos del día local observado.
- Satélite: IMERG Early todavía no está (TASK-009), así que queda sin dato.
- Pronóstico: emisión `operativa` para ese día y el umbral de decisión del RF calibrado,
  fijado fuera de la prueba (`EVALUATION_FILE`).
- Nivel del río: subida máxima en 24 h del día (`LEVEL_DAILY_FILE`, TASK-038), solo
  para reportes que afirman creciente (TASK-039).
Si falta un artefacto, esa fuente queda sin dato: la confianza solo usa lo que hay.
"""

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from climapp.data.daily import read_daily_csv
from climapp.data.level import read_level_csv
from climapp.logging import get_logger
from climapp.verification.confidence import Evidence
from climapp.verification.schemas import ReportStructured

log = get_logger(__name__)
LIVE_VARIANT = "operativa"


def report_says_rain(structured: ReportStructured) -> bool:
    """`True` si el reporte afirma que llueve (o granizó) con alguna intensidad."""
    return structured.event_type != "sin_lluvia" and structured.intensity != "ninguna"


def report_says_flood(structured: ReportStructured) -> bool:
    """`True` si el reporte afirma una creciente del río."""
    return structured.event_type == "crecida"


def _json(path: Path) -> Any:
    """JSON de un artefacto, o `None` si falta o está corrupto."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        log.warning("evidence.artifact_missing", path=path.name, error=type(err).__name__)
        return None


@dataclass(frozen=True, slots=True)
class EvidenceSources:
    """Artefactos de donde sale la evidencia y la zona horaria del día local."""

    daily_file: Path
    forecasts_file: Path
    evaluation_file: Path
    level_file: Path
    level_series: str
    tz: ZoneInfo

    def _stations(self, day: date) -> dict[str, float]:
        """Lluvia de las estaciones válidas y no imputadas en el día."""
        try:
            rows = read_daily_csv(self.daily_file)
        except (OSError, ValidationError) as err:
            log.warning("evidence.daily_missing", error=type(err).__name__)
            return {}
        return {
            r.series_id: r.precip_mm
            for r in rows
            if r.date == day and r.valid and not r.imputed and r.precip_mm is not None
        }

    def _forecast(self, day: date) -> tuple[float | None, float]:
        """Probabilidad operativa para el día y umbral de decisión del RF calibrado."""
        records, report = _json(self.forecasts_file) or [], _json(self.evaluation_file) or {}
        probs = [
            r["prob_ge_threshold"]
            for r in records
            if r.get("variant") == LIVE_VARIANT and r.get("target_date") == day.isoformat()
        ]
        thresholds = [
            m["threshold"]
            for m in report.get("scenarios", {}).get("con_est_b", [])
            if m.get("name") == "rf" and m.get("variant") == LIVE_VARIANT and m.get("calibrated")
        ]
        if not probs or not thresholds:
            return None, 0.0
        return float(probs[0]), float(thresholds[0])

    def _level_rise(self, day: date) -> float | None:
        """Subida máxima en 24 h de la serie `level_series` en el día, o `None` si no hay dato."""
        try:
            rows = read_level_csv(self.level_file)
        except (OSError, KeyError, ValueError) as err:
            log.warning("evidence.level_missing", error=type(err).__name__)
            return None
        rises = [
            r.rise_24h_max_m for r in rows if r.date == day and r.series_id == self.level_series
        ]
        return max(rises) if rises else None

    def evidence_for(self, structured: ReportStructured) -> Evidence:
        """Evidencia para el día local en que el ciudadano dice haber observado."""
        day = structured.observed_at.astimezone(self.tz).date()
        prob, threshold = self._forecast(day)
        return Evidence(
            report_rain=report_says_rain(structured),
            station_mm=self._stations(day),
            satellite_mm=None,
            forecast_prob=prob,
            forecast_threshold=threshold,
            report_flood=report_says_flood(structured),
            level_rise_m=self._level_rise(day),
        )
