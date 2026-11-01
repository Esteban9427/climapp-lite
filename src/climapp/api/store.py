"""Almacén de reportes en SQLite (`DATA_DIR/climapp.db`, fuera de git; data-model).

Cada reporte se guarda como JSON junto con su día local de recepción, para filtrar por
fecha. Una conexión por operación: el servidor y las tareas en segundo plano no comparten
cursores.
"""

import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from climapp.api.schemas import ReportRecord, ReportStatus

MAX_ROWS = 1_000_000  # tope de filas al vaciar la base local
SCHEMA = """CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY, received_at TEXT NOT NULL, local_day TEXT NOT NULL,
    status TEXT NOT NULL, record TEXT NOT NULL)"""


class ReportStore:
    """Reportes guardados en SQLite."""

    def __init__(self, path: Path, tz: ZoneInfo) -> None:
        """Crea la base y la tabla si faltan; `tz` define el día local de recepción."""
        self._path, self._tz = path, tz
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.execute(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        """Conexión nueva a la base."""
        return sqlite3.connect(self._path)

    def _row(self, record: ReportRecord) -> tuple[str, str, str, str, str]:
        """Fila de la tabla para un reporte."""
        day = record.received_at.astimezone(self._tz).date().isoformat()
        stamp = record.received_at.isoformat()
        return str(record.id), stamp, day, record.status, record.model_dump_json()

    def add(self, record: ReportRecord) -> None:
        """Guarda un reporte nuevo."""
        with closing(self._connect()) as conn, conn:
            conn.execute("INSERT INTO reports VALUES (?, ?, ?, ?, ?)", self._row(record))

    def update(self, record: ReportRecord) -> None:
        """Reemplaza un reporte existente."""
        row = self._row(record)
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE reports SET received_at=?, local_day=?, status=?, record=? WHERE id=?",
                (*row[1:], row[0]),
            )

    def get(self, report_id: UUID) -> ReportRecord | None:
        """El reporte, o `None` si no existe."""
        with closing(self._connect()) as conn:
            found = conn.execute(
                "SELECT record FROM reports WHERE id=?", (str(report_id),)
            ).fetchone()
        return ReportRecord.model_validate_json(found[0]) if found else None

    def received_since(self, since: datetime) -> list[ReportRecord]:
        """Reportes recibidos desde `since` (incluido), el más reciente primero."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT record FROM reports WHERE received_at>=? ORDER BY received_at DESC",
                (since.astimezone(UTC).isoformat(),),
            ).fetchall()
        return [ReportRecord.model_validate_json(r[0]) for r in rows]

    def clear(self) -> list[ReportRecord]:
        """Borra todos los reportes y devuelve los borrados (para limpiar sus fotos)."""
        removed = self.list(None, None, None, MAX_ROWS)
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM reports")
        return removed

    def list(
        self, status: ReportStatus | None, date_from: date | None, date_to: date | None, limit: int
    ) -> list[ReportRecord]:
        """Reportes filtrados por estado y día local de recepción, el más reciente primero."""
        clauses, params = ["1=1"], []
        for clause, value in (
            ("status=?", status),
            ("local_day>=?", date_from),
            ("local_day<=?", date_to),
        ):
            if value is not None:
                clauses.append(clause)
                params.append(str(value) if not isinstance(value, date) else value.isoformat())
        where = " AND ".join(clauses)  # solo cláusulas fijas; los valores van como parámetros
        sql = f"SELECT record FROM reports WHERE {where} ORDER BY received_at DESC LIMIT ?"  # noqa: S608
        with closing(self._connect()) as conn:
            rows = conn.execute(sql, (*params, limit)).fetchall()
        return [ReportRecord.model_validate_json(r[0]) for r in rows]
