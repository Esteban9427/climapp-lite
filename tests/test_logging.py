"""Tests de la configuración de structlog (TASK-001)."""

import json

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
