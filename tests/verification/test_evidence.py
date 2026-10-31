"""Tests de la evidencia de un reporte para la confianza (TASK-016 + TASK-014)."""

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from climapp.data.daily import write_daily_csv
from climapp.data.models import DailyPrecip
from climapp.verification.evidence import EvidenceSources, report_says_rain
from climapp.verification.schemas import ReportStructured

TZ = ZoneInfo("America/Bogota")
DAY = date(2024, 12, 31)


def _row(series: str, mm: float | None, day: date = DAY) -> DailyPrecip:
    return DailyPrecip(
        date=day,
        series_id=series,
        precip_mm=mm,
        n_readings=144 if mm is not None else 3,
        valid=mm is not None,
        imputed=False,
        source_hash="h",
        n_suspect=0,
        suspect_mm=0.0,
        n_gap=0,
    )


def _structured(
    event: str = "lluvia", intensity: str = "fuerte", hour: int = 16
) -> ReportStructured:
    return ReportStructured(
        event_type=event,
        intensity=intensity,  # type: ignore[arg-type]
        observed_at=datetime(2024, 12, 31, hour, 0, tzinfo=TZ),
        claims=["llueve"],
        numbers_cited=[],
    )


def _sources(tmp_path: Path) -> EvidenceSources:
    daily = write_daily_csv(
        [_row("EST-A", 14.0), _row("EST-B", None), _row("EST-C", 3.0, date(2024, 12, 30))],
        tmp_path / "daily.csv",
    )
    forecasts = tmp_path / "forecasts.json"
    forecasts.write_text(
        json.dumps(
            [
                {
                    "variant": "operativa",
                    "issue_date": "2024-12-30",
                    "target_date": "2024-12-31",
                    "prob_ge_threshold": 0.2,
                },
                {
                    "variant": "historica",
                    "issue_date": "2024-12-30",
                    "target_date": "2024-12-31",
                    "prob_ge_threshold": 0.9,
                },
            ]
        ),
        encoding="utf-8",
    )
    evaluation = tmp_path / "evaluation.json"
    evaluation.write_text(
        json.dumps(
            {
                "scenarios": {
                    "con_est_b": [
                        {
                            "name": "rf",
                            "variant": "operativa",
                            "calibrated": True,
                            "threshold": 0.13,
                        },
                        {
                            "name": "rf",
                            "variant": "operativa",
                            "calibrated": False,
                            "threshold": 0.5,
                        },
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    return EvidenceSources(
        daily_file=daily, forecasts_file=forecasts, evaluation_file=evaluation, tz=TZ
    )


def test_evidence_uses_valid_stations_of_the_observed_local_day(tmp_path: Path) -> None:
    evidence = _sources(tmp_path).evidence_for(_structured())
    assert evidence.station_mm == {"EST-A": 14.0}
    assert evidence.report_rain is True
    assert evidence.satellite_mm is None  # IMERG Early aún no está (TASK-009)


def test_evidence_uses_the_operational_forecast_and_its_calibrated_threshold(
    tmp_path: Path,
) -> None:
    evidence = _sources(tmp_path).evidence_for(_structured())
    assert (evidence.forecast_prob, evidence.forecast_threshold) == (0.2, 0.13)


def test_missing_artifacts_give_empty_evidence(tmp_path: Path) -> None:
    sources = EvidenceSources(tmp_path / "a", tmp_path / "b", tmp_path / "c", TZ)
    evidence = sources.evidence_for(_structured())
    assert (evidence.station_mm, evidence.forecast_prob) == ({}, None)


def test_report_says_rain_only_with_rain_and_some_intensity() -> None:
    assert report_says_rain(_structured("lluvia", "debil"))
    assert report_says_rain(_structured("granizo", "moderada"))
    assert not report_says_rain(_structured("sin_lluvia", "ninguna"))
    assert not report_says_rain(_structured("lluvia", "ninguna"))
