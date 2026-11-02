"""Tests de la configuración de structlog (TASK-001)."""

import json
from datetime import date

import pytest

from climapp.logging import configure_logging, get_logger


def test_events_are_emitted_as_json(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging()
    get_logger("test").info("report.verified", report_id="r-1", attempts=2)
    event = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert event["event"] == "report.verified"
    assert event["report_id"] == "r-1"
    assert event["attempts"] == 2
    assert event["level"] == "info"
    assert "timestamp" in event


def test_a_module_logger_created_before_configuring_still_emits_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Revisión de Muse del día 3c: los `log = get_logger(__name__)` se crean al importar."""
    early = get_logger("creado.antes")
    configure_logging()
    early.info("imerg.written", days=45)
    event = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert (event["event"], event["logger"], event["days"]) == ("imerg.written", "creado.antes", 45)


def test_dates_are_serialized_instead_of_crashing(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging()
    get_logger("test").info("imerg.written", latest=date(2026, 10, 31))
    event = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert event["latest"] == "2026-10-31"
