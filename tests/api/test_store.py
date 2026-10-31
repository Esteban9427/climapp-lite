"""Tests del almacén SQLite de reportes (TASK-016, data-model: DATA_DIR/climapp.db)."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from climapp.api.schemas import ReportRecord
from climapp.api.store import ReportStore

T0 = datetime(2024, 12, 31, 21, 0, tzinfo=UTC)  # 16:00 en Cali


def _record(status: str = "verificando", received: datetime = T0) -> ReportRecord:
    return ReportRecord(
        id=uuid4(),
        received_at=received,
        lat=1.234567,
        lon=-1.765432,
        status=status,  # type: ignore[arg-type]
        reject_reason=None,
        structured=None,
        confidence=None,
        attempts=[],
        fallback=False,
        text="llueve",
        photo_file=None,
    )


def test_add_get_and_update_round_trip(tmp_path: Path) -> None:
    store = ReportStore(tmp_path / "db" / "climapp.db")
    record = _record()
    store.add(record)
    assert store.get(record.id) == record
    done = record.model_copy(update={"status": "verificado"})
    store.update(done)
    assert store.get(record.id) == done


def test_missing_report_is_none(tmp_path: Path) -> None:
    assert ReportStore(tmp_path / "c.db").get(uuid4()) is None


def test_list_filters_by_status_local_dates_and_limit(tmp_path: Path) -> None:
    store = ReportStore(tmp_path / "c.db")
    old = _record("verificado", T0 - timedelta(days=2))
    ok = _record("verificado")
    late = _record("verificado", datetime(2025, 1, 1, 4, 0, tzinfo=UTC))  # 23:00 del 31 en Cali
    rejected = _record("rechazado")
    for r in (old, ok, late, rejected):
        store.add(r)
    day = date(2024, 12, 31)
    listed = store.list(status="verificado", date_from=day, date_to=day, limit=100)
    assert [r.id for r in listed] == [late.id, ok.id]  # más reciente primero
    assert len(store.list(status=None, date_from=None, date_to=None, limit=2)) == 2
