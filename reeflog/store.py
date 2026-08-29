import sqlite3
import threading
import time
from dataclasses import dataclass

from .parameters import PARAMETERS

SCHEMA = """
CREATE TABLE IF NOT EXISTS reading (
    id INTEGER PRIMARY KEY,
    parameter TEXT NOT NULL,
    value REAL NOT NULL,
    basis TEXT NOT NULL,
    measured_at INTEGER NOT NULL,
    entered_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS reading_by_parameter
    ON reading (parameter, measured_at DESC);
"""


@dataclass(frozen=True)
class Reading:
    id: int
    parameter: str
    value: float
    basis: str
    measured_at: int
    entered_at: int


class Store:
    def __init__(self, path: str) -> None:
        # ThreadingHTTPServer serves each request on its own thread; one
        # connection guarded by a lock keeps SQLite's single writer honest.
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            # readOnlyRootFilesystem leaves no writable temp dir, and SQLite
            # would otherwise reach for one to spill sort results into.
            self._db.execute("PRAGMA temp_store = MEMORY")
            self._db.executescript(SCHEMA)
            self._migrate()
            self._db.commit()

    def _migrate(self) -> None:
        """
        CREATE TABLE IF NOT EXISTS does not reshape a table that already exists,
        so renaming a column in SCHEMA silently leaves old databases behind and
        every INSERT then fails. 0.1.0 called this column `compound`.
        """
        columns = {r[1] for r in self._db.execute("PRAGMA table_info(reading)")}
        if "compound" in columns and "basis" not in columns:
            self._db.execute("ALTER TABLE reading RENAME COLUMN compound TO basis")

    def add(self, key: str, value: float, measured_at: int | None = None) -> Reading:
        parameter = PARAMETERS.get(key)
        if parameter is None:
            raise ValueError(f"unknown parameter {key!r}")
        parameter.check(value)

        now = int(time.time())
        measured = int(measured_at if measured_at is not None else now)
        if measured > now + 86400:
            raise ValueError("measured time is in the future")

        with self._lock:
            cur = self._db.execute(
                "INSERT INTO reading (parameter, value, basis, measured_at, entered_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (parameter.key, float(value), parameter.basis, measured, now),
            )
            self._db.commit()
            row_id = cur.lastrowid
        return Reading(row_id, parameter.key, float(value), parameter.basis, measured, now)

    def latest(self) -> dict[str, Reading]:
        """Newest reading per parameter, by measurement time."""
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM reading r WHERE measured_at = ("
                "  SELECT MAX(measured_at) FROM reading WHERE parameter = r.parameter"
                ") GROUP BY parameter"
            ).fetchall()
        return {r["parameter"]: _reading(r) for r in rows}

    def recent(self, limit: int = 25) -> list[Reading]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM reading ORDER BY measured_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_reading(r) for r in rows]

    def healthy(self) -> bool:
        try:
            with self._lock:
                self._db.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def close(self) -> None:
        with self._lock:
            self._db.close()


def _reading(row: sqlite3.Row) -> Reading:
    return Reading(
        row["id"],
        row["parameter"],
        row["value"],
        row["basis"],
        row["measured_at"],
        row["entered_at"],
    )
