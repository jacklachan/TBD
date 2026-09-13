"""Small case memory: what was decided before, and why it was rejected.

Retrieval is by constraint tag and scenario family, not by embedding -- with a
handful of cases that is both sufficient and inspectable, and a judge can read
the row that produced a suggestion.

The rule that matters: memory *suggests*, it never applies. A prior operator's
limit is surfaced with its case ID so the current operator can accept it. It is
never silently folded into the active policy.
"""

from __future__ import annotations

import functools
import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS case_memory (
    memory_id      TEXT PRIMARY KEY,
    case_id        TEXT NOT NULL,
    scenario_id    TEXT NOT NULL,
    scenario_family TEXT NOT NULL,
    outcome        TEXT NOT NULL,
    candidate_id   TEXT,
    tags           TEXT NOT NULL,
    summary        TEXT NOT NULL,
    detail_json    TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_case_memory_family ON case_memory(scenario_family);
"""

# A row is filed per completed run, so the table needs a ceiling. Retrieval
# only ever reads the three most relevant rows in a family; older ones are
# history nobody queries, and an unbounded demo database is a slow leak.
MAX_RECORDS = 500

TAG_BUDGET_REDUCED = "BUDGET_REDUCED"
TAG_WINDOW_BLOCKED = "WINDOW_BLOCKED"
TAG_SECONDARY_CONFLICT = "SECONDARY_CONFLICT"
TAG_NO_FEASIBLE_OPTION = "NO_FEASIBLE_OPTION"
TAG_OPERATOR_REJECTED = "OPERATOR_REJECTED"


def _synchronized(method):
    """Serialise one method against the shared connection. See backend/store.py."""

    @functools.wraps(method)
    def guarded(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return guarded


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    case_id: str
    scenario_id: str
    scenario_family: str
    outcome: str
    candidate_id: str | None
    tags: tuple[str, ...]
    summary: str
    detail: dict
    created_at_utc: str

    def as_hit(self) -> dict:
        """The compact shape handed to the model in a briefing."""
        return {
            "case_id": self.case_id,
            "memory_id": self.memory_id,
            "outcome": self.outcome,
            "tags": list(self.tags),
            "summary": self.summary,
            "suggestion": self.detail.get("suggestion", ""),
        }


class CaseMemory:
    """SQLite-backed. Pass ``:memory:`` for tests."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        # Runs are executed on a worker thread, so the connection must not be
        # pinned to the creating thread -- and unpinning it is not on its own
        # thread safety, so every method below takes this lock.
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(SCHEMA)
        self._connection.commit()

    @_synchronized
    def close(self) -> None:
        self._connection.close()

    @_synchronized
    def record(
        self,
        case_id: str,
        scenario_id: str,
        outcome: str,
        summary: str,
        tags: tuple[str, ...] = (),
        candidate_id: str | None = None,
        detail: dict | None = None,
        scenario_family: str | None = None,
    ) -> MemoryRecord:
        entry = MemoryRecord(
            memory_id=f"mem_{uuid.uuid4().hex[:10]}",
            case_id=case_id,
            scenario_id=scenario_id,
            scenario_family=scenario_family or scenario_id,
            outcome=outcome,
            candidate_id=candidate_id,
            tags=tuple(tags),
            summary=summary,
            detail=detail or {},
            created_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        self._connection.execute(
            "INSERT INTO case_memory (memory_id, case_id, scenario_id, scenario_family,"
            " outcome, candidate_id, tags, summary, detail_json, created_at_utc)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                entry.memory_id,
                entry.case_id,
                entry.scenario_id,
                entry.scenario_family,
                entry.outcome,
                entry.candidate_id,
                json.dumps(list(entry.tags)),
                entry.summary,
                json.dumps(entry.detail),
                entry.created_at_utc,
            ),
        )
        self._connection.commit()
        self._prune()
        return entry

    def _prune(self, keep: int = MAX_RECORDS) -> None:
        """Drop the oldest rows beyond the cap. Called under the record lock."""
        self._connection.execute(
            "DELETE FROM case_memory WHERE rowid NOT IN ("
            " SELECT rowid FROM case_memory ORDER BY rowid DESC LIMIT ?)",
            (keep,),
        )
        self._connection.commit()

    @_synchronized
    def relevant(
        self,
        scenario_family: str,
        tags: tuple[str, ...] = (),
        exclude_case_id: str | None = None,
        limit: int = 3,
    ) -> list[MemoryRecord]:
        """Prior cases in the same family, most recent first.

        A tag overlap ranks a record higher; nothing is filtered out purely for
        lacking a tag, because the useful precedent is often the one whose tags
        were not anticipated.
        """
        rows = self._connection.execute(
            "SELECT * FROM case_memory WHERE scenario_family = ?"
            " ORDER BY created_at_utc DESC, rowid DESC",
            (scenario_family,),
        ).fetchall()

        wanted = set(tags)
        records = [self._from_row(row) for row in rows]
        records = [r for r in records if r.case_id != exclude_case_id]
        # One row is filed per run, so a case that was planned twice appeared
        # twice in the briefing. Keep the most recent run of each case; rows
        # arrive newest first.
        seen: set[str] = set()
        records = [r for r in records if not (r.case_id in seen or seen.add(r.case_id))]
        records.sort(
            key=lambda r: (len(wanted.intersection(r.tags)), r.created_at_utc),
            reverse=True,
        )
        return records[:limit]

    @_synchronized
    def all_records(self) -> list[MemoryRecord]:
        rows = self._connection.execute(
            "SELECT * FROM case_memory ORDER BY created_at_utc DESC, rowid DESC"
        ).fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            memory_id=row["memory_id"],
            case_id=row["case_id"],
            scenario_id=row["scenario_id"],
            scenario_family=row["scenario_family"],
            outcome=row["outcome"],
            candidate_id=row["candidate_id"],
            tags=tuple(json.loads(row["tags"])),
            summary=row["summary"],
            detail=json.loads(row["detail_json"]),
            created_at_utc=row["created_at_utc"],
        )
