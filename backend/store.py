"""SQLite persistence for cases, events, evidence, proposals and executions.

Three properties this layer is responsible for.

*Evidence is addressable.* Every validation is stored under its
``validation_id`` and every event carries the IDs it refers to, so a proposal
can be traced back to the numbers that justified it without recomputation.

*Execution happens once.* Approval is a single transaction that checks versions,
checks the deterministic verdict, and inserts an execution row guarded by a
unique idempotency key. A repeated request with the same key returns the record
that already exists; the same key with different content is a conflict.

*History survives policy changes.* Confirming a new policy invalidates pending
proposals but never rewrites a committed execution.
"""

from __future__ import annotations

import functools
import json
import sqlite3
import threading
import uuid
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.planning.policy import BurnWindow, Policy
from backend.planning.verifier import ValidationResult, VerifiedEncounter

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS cases (
    case_id          TEXT PRIMARY KEY,
    scenario_id      TEXT NOT NULL,
    scenario_version INTEGER NOT NULL,
    policy_version   INTEGER NOT NULL,
    grid_revision    INTEGER NOT NULL DEFAULT 1,
    document_json    TEXT NOT NULL,
    policy_json      TEXT NOT NULL,
    pending_diff_json TEXT,
    parent_case_id   TEXT,
    created_at_utc   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    event_id       TEXT PRIMARY KEY,
    case_id        TEXT NOT NULL,
    run_id         TEXT,
    sequence       INTEGER NOT NULL,
    event_type     TEXT NOT NULL,
    summary        TEXT NOT NULL,
    duration_ms    REAL NOT NULL DEFAULT 0,
    details_json   TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL,
    UNIQUE (case_id, sequence)
);

CREATE TABLE IF NOT EXISTS validations (
    validation_id  TEXT PRIMARY KEY,
    case_id        TEXT NOT NULL,
    candidate_id   TEXT NOT NULL,
    status         TEXT NOT NULL,
    payload_json   TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS proposals (
    proposal_id      TEXT PRIMARY KEY,
    case_id          TEXT NOT NULL,
    scenario_version INTEGER NOT NULL,
    policy_version   INTEGER NOT NULL,
    candidate_id     TEXT NOT NULL,
    validation_id    TEXT NOT NULL,
    status           TEXT NOT NULL,
    payload_json     TEXT NOT NULL,
    created_at_utc   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS executions (
    execution_id    TEXT PRIMARY KEY,
    case_id         TEXT NOT NULL,
    proposal_id     TEXT NOT NULL,
    candidate_id    TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    mode            TEXT NOT NULL DEFAULT 'SIMULATION',
    executed_at_utc TEXT NOT NULL,
    UNIQUE (case_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_events_case ON events(case_id, sequence);
CREATE INDEX IF NOT EXISTS idx_validations_case ON validations(case_id);
CREATE INDEX IF NOT EXISTS idx_proposals_case ON proposals(case_id);
"""

PROPOSAL_READY = "READY"
PROPOSAL_BLOCKED = "BLOCKED"
PROPOSAL_STALE = "STALE"
PROPOSAL_EXECUTED = "EXECUTED"


def _synchronized(method):
    """Serialise one method against the single shared connection.

    The API runs plans on a worker pool and every thread uses the same
    connection. SQLite itself tolerates that; the read-modify-write inside
    ``append_events`` does not. Two runs on one case read the same last
    sequence number, and the loser's entire trace is then rejected by the
    UNIQUE constraint -- the events are simply lost and the run is marked
    FAILED. Making each method one atomic unit of work is what prevents that.
    """

    @functools.wraps(method)
    def guarded(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return guarded


class StoreError(RuntimeError):
    """Persistence rejected the operation."""


class IdempotencyConflict(StoreError):
    """The same idempotency key was reused for different content."""


class CapacityError(StoreError):
    """The demo's bounded case store is full."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _encode(value: Any) -> Any:
    """JSON-safe form of dataclasses, tuples and nested structures."""
    if is_dataclass(value) and not isinstance(value, type):
        return {k: _encode(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {k: _encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(v) for v in value]
    return value


def policy_to_json(policy: Policy) -> str:
    return json.dumps(
        {
            "policy_version": policy.policy_version,
            "max_delta_v_mps": policy.max_delta_v_mps,
            "min_separation_m": policy.min_separation_m,
            "blocked_windows": [
                {
                    "window_id": w.window_id,
                    "label": w.label,
                    "start_s": w.start_s,
                    "end_s": w.end_s,
                }
                for w in policy.blocked_windows
            ],
        }
    )


def policy_from_json(text: str) -> Policy:
    data = json.loads(text)
    return Policy(
        policy_version=int(data["policy_version"]),
        max_delta_v_mps=float(data["max_delta_v_mps"]),
        min_separation_m=float(data["min_separation_m"]),
        blocked_windows=tuple(
            BurnWindow(
                window_id=w["window_id"],
                label=w["label"],
                start_s=float(w["start_s"]),
                end_s=float(w["end_s"]),
            )
            for w in data.get("blocked_windows", ())
        ),
    )


def validation_to_json(validation: ValidationResult) -> str:
    return json.dumps(_encode(validation))


def validation_from_json(text: str) -> ValidationResult:
    data = json.loads(text)
    encounters = tuple(VerifiedEncounter(**e) for e in data.pop("encounters", ()))
    data["reason_codes"] = tuple(data.get("reason_codes", ()))
    data["evaluated_object_ids"] = tuple(data.get("evaluated_object_ids", ()))
    return ValidationResult(encounters=encounters, **data)


@dataclass(frozen=True)
class CaseRow:
    case_id: str
    scenario_id: str
    scenario_version: int
    policy_version: int
    grid_revision: int
    document: dict
    policy: Policy
    pending_diff: dict | None
    parent_case_id: str | None
    created_at_utc: str


@dataclass(frozen=True)
class ExecutionRecord:
    execution_id: str
    case_id: str
    proposal_id: str
    candidate_id: str
    idempotency_key: str
    mode: str
    executed_at_utc: str


class Store:
    """One connection, short transactions. Pass ``:memory:`` for tests."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        # Reentrant: create_case calls get_case, and record_execution reads
        # back a row it may have just written.
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(SCHEMA)
        self._connection.commit()

    @_synchronized
    def close(self) -> None:
        self._connection.close()

    # ----------------------------------------------------------------- cases

    @_synchronized
    def create_case(
        self,
        document: dict,
        policy: Policy,
        parent_case_id: str | None = None,
        case_id: str | None = None,
        max_cases: int | None = None,
    ) -> CaseRow:
        if max_cases is not None:
            count = self._connection.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
            if count >= max_cases:
                raise CapacityError("The demo has reached its case limit. Archive the store before starting another session.")
        row_id = case_id or f"case_{uuid.uuid4().hex[:10]}"
        created = _now()
        self._connection.execute(
            "INSERT INTO cases (case_id, scenario_id, scenario_version, policy_version,"
            " grid_revision, document_json, policy_json, pending_diff_json,"
            " parent_case_id, created_at_utc) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                row_id,
                str(document["scenario_id"]),
                int(document["scenario_version"]),
                policy.policy_version,
                1,
                json.dumps(document),
                policy_to_json(policy),
                None,
                parent_case_id,
                created,
            ),
        )
        self._connection.commit()
        return self.get_case(row_id)

    @_synchronized
    def get_case(self, case_id: str) -> CaseRow:
        row = self._connection.execute(
            "SELECT * FROM cases WHERE case_id = ?", (case_id,)
        ).fetchone()
        if row is None:
            raise StoreError(f"unknown case {case_id!r}")
        return CaseRow(
            case_id=row["case_id"],
            scenario_id=row["scenario_id"],
            scenario_version=row["scenario_version"],
            policy_version=row["policy_version"],
            grid_revision=row["grid_revision"],
            document=json.loads(row["document_json"]),
            policy=policy_from_json(row["policy_json"]),
            pending_diff=json.loads(row["pending_diff_json"])
            if row["pending_diff_json"]
            else None,
            parent_case_id=row["parent_case_id"],
            created_at_utc=row["created_at_utc"],
        )

    @_synchronized
    def case_exists(self, case_id: str) -> bool:
        return (
            self._connection.execute(
                "SELECT 1 FROM cases WHERE case_id = ?", (case_id,)
            ).fetchone()
            is not None
        )

    @_synchronized
    def update_policy(self, case_id: str, policy: Policy, expected_policy_version: int | None = None) -> None:
        """Apply a confirmed policy and stand down everything computed under the old one.

        Pending proposals become STALE rather than disappearing, so the trace
        still shows what was superseded. Executions are untouched: a burn that
        happened stays happened.
        """
        with self._connection:
            current = self.get_case(case_id)
            if expected_policy_version is not None and current.policy_version != expected_policy_version:
                raise StoreError("The policy changed while this request was running.")
            if policy.policy_version != current.policy_version + 1:
                raise StoreError("A policy change must advance the current version exactly once.")
            self._connection.execute(
                "UPDATE cases SET policy_json = ?, policy_version = ?,"
                " pending_diff_json = NULL, grid_revision = 1 WHERE case_id = ?",
                (policy_to_json(policy), policy.policy_version, case_id),
            )
            self._connection.execute(
                "UPDATE proposals SET status = ? WHERE case_id = ? AND status IN (?, ?)",
                (PROPOSAL_STALE, case_id, PROPOSAL_READY, PROPOSAL_BLOCKED),
            )

    @_synchronized
    def set_pending_diff(self, case_id: str, diff: dict | None) -> None:
        self._connection.execute(
            "UPDATE cases SET pending_diff_json = ? WHERE case_id = ?",
            (json.dumps(diff) if diff else None, case_id),
        )
        self._connection.commit()

    @_synchronized
    def set_grid_revision(self, case_id: str, grid_revision: int, expected_policy_version: int | None = None) -> None:
        if expected_policy_version is not None and self.get_case(case_id).policy_version != expected_policy_version:
            return
        self._connection.execute(
            "UPDATE cases SET grid_revision = ? WHERE case_id = ?",
            (grid_revision, case_id),
        )
        self._connection.commit()

    # ---------------------------------------------------------------- events

    @_synchronized
    def append_events(self, case_id: str, run_id: str | None, events: list) -> int:
        """Append with a monotonic per-case sequence. Returns how many landed."""
        cursor = self._connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) AS last FROM events WHERE case_id = ?",
            (case_id,),
        )
        sequence = int(cursor.fetchone()["last"])

        with self._connection:
            for event in events:
                sequence += 1
                self._connection.execute(
                    "INSERT INTO events (event_id, case_id, run_id, sequence, event_type,"
                    " summary, duration_ms, details_json, created_at_utc)"
                    " VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        f"evt_{uuid.uuid4().hex[:12]}",
                        case_id,
                        run_id,
                        sequence,
                        getattr(event, "event_type", "event"),
                        getattr(event, "summary", ""),
                        float(getattr(event, "duration_ms", 0.0)),
                        json.dumps(_encode(getattr(event, "details", {}))),
                        getattr(event, "created_at_utc", None) or _now(),
                    ),
                )
        return len(events)

    @_synchronized
    def events(self, case_id: str) -> list[dict]:
        rows = self._connection.execute(
            "SELECT * FROM events WHERE case_id = ? ORDER BY sequence", (case_id,)
        ).fetchall()
        return [
            {
                "event_id": r["event_id"],
                "run_id": r["run_id"],
                "sequence": r["sequence"],
                "event_type": r["event_type"],
                "summary": r["summary"],
                "duration_ms": r["duration_ms"],
                "details": json.loads(r["details_json"]),
                "created_at_utc": r["created_at_utc"],
            }
            for r in rows
        ]

    # ----------------------------------------------------------- validations

    @_synchronized
    def save_validation(self, case_id: str, validation: ValidationResult) -> None:
        self._connection.execute(
            "INSERT OR REPLACE INTO validations (validation_id, case_id, candidate_id,"
            " status, payload_json, created_at_utc) VALUES (?,?,?,?,?,?)",
            (
                validation.validation_id,
                case_id,
                validation.candidate_id,
                validation.status,
                validation_to_json(validation),
                validation.computed_at_utc,
            ),
        )
        self._connection.commit()

    @_synchronized
    def get_validation(self, validation_id: str) -> ValidationResult:
        row = self._connection.execute(
            "SELECT payload_json FROM validations WHERE validation_id = ?",
            (validation_id,),
        ).fetchone()
        if row is None:
            raise StoreError(f"unknown validation {validation_id!r}")
        return validation_from_json(row["payload_json"])

    @_synchronized
    def validations(self, case_id: str) -> list[ValidationResult]:
        rows = self._connection.execute(
            "SELECT payload_json FROM validations WHERE case_id = ? ORDER BY created_at_utc",
            (case_id,),
        ).fetchall()
        return [validation_from_json(r["payload_json"]) for r in rows]

    # ------------------------------------------------------------- proposals

    @_synchronized
    def save_proposal(self, case_id: str, proposal) -> None:
        case = self.get_case(case_id)
        status = proposal.status
        if (case.scenario_version, case.policy_version) != (proposal.scenario_version, proposal.policy_version):
            status = PROPOSAL_STALE
        self._connection.execute(
            "INSERT OR REPLACE INTO proposals (proposal_id, case_id, scenario_version,"
            " policy_version, candidate_id, validation_id, status, payload_json,"
            " created_at_utc) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                proposal.proposal_id,
                case_id,
                proposal.scenario_version,
                proposal.policy_version,
                proposal.candidate_id,
                proposal.validation_id,
                status,
                json.dumps(_encode(proposal)),
                _now(),
            ),
        )
        self._connection.commit()

    @_synchronized
    def get_proposal(self, proposal_id: str) -> dict:
        row = self._connection.execute(
            "SELECT * FROM proposals WHERE proposal_id = ?", (proposal_id,)
        ).fetchone()
        if row is None:
            raise StoreError(f"unknown proposal {proposal_id!r}")
        payload = json.loads(row["payload_json"])
        payload["status"] = row["status"]
        return payload

    @_synchronized
    def latest_proposal(self, case_id: str) -> dict | None:
        case = self.get_case(case_id)
        row = self._connection.execute(
            "SELECT * FROM proposals WHERE case_id = ? ORDER BY (policy_version = ?) DESC, created_at_utc DESC,"
            " rowid DESC LIMIT 1",
            (case_id, case.policy_version),
        ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        payload["status"] = row["status"]
        return payload

    @_synchronized
    def mark_proposal(self, proposal_id: str, status: str) -> None:
        self._connection.execute(
            "UPDATE proposals SET status = ? WHERE proposal_id = ?", (status, proposal_id)
        )
        self._connection.commit()

    # ------------------------------------------------------------ executions

    @_synchronized
    def record_execution(
        self,
        case_id: str,
        proposal_id: str,
        candidate_id: str,
        idempotency_key: str,
    ) -> tuple[ExecutionRecord, bool]:
        """Recheck evidence and record the single case execution atomically."""
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            return self._record_execution_locked(case_id, proposal_id, candidate_id, idempotency_key)

    def _record_execution_locked(
        self, case_id: str, proposal_id: str, candidate_id: str, idempotency_key: str
    ) -> tuple[ExecutionRecord, bool]:
        """Insert exactly one execution. Returns (record, created).

        A repeat with the same key and the same proposal returns the existing
        record with ``created`` false. The same key against a different proposal
        is a conflict, not a silent overwrite.
        """
        content_hash = f"{proposal_id}:{candidate_id}"
        existing = self._connection.execute(
            "SELECT * FROM executions WHERE case_id = ? AND idempotency_key = ?",
            (case_id, idempotency_key),
        ).fetchone()

        if existing is not None:
            if existing["content_hash"] != content_hash:
                raise IdempotencyConflict(
                    f"idempotency key {idempotency_key!r} was already used for a "
                    f"different proposal in this case"
                )
            return self._execution_from_row(existing), False

        prior_execution = self.execution_for_case(case_id)
        if prior_execution is not None:
            if (prior_execution.proposal_id, prior_execution.candidate_id) == (proposal_id, candidate_id):
                return prior_execution, False
            raise StoreError("This case has already executed. Reset to start a new simulation.")

        case = self.get_case(case_id)
        proposal = self.get_proposal(proposal_id)
        evidence_row = self._connection.execute(
            "SELECT case_id FROM validations WHERE validation_id = ?", (proposal["validation_id"],)
        ).fetchone()
        validation = self.get_validation(proposal["validation_id"])
        if proposal["case_id"] != case_id or proposal["candidate_id"] != candidate_id:
            raise StoreError("Proposal identity does not match the requested execution.")
        if proposal["status"] != PROPOSAL_READY:
            raise StoreError("Only a ready proposal can be executed.")
        if (proposal["scenario_version"], proposal["policy_version"]) != (case.scenario_version, case.policy_version):
            raise StoreError("The proposal is stale.")
        if (evidence_row is None or evidence_row["case_id"] != case_id
                or validation.candidate_id != candidate_id
                or validation.scenario_id != case.scenario_id
                or validation.scenario_version != case.scenario_version
                or validation.policy_version != case.policy_version
                or validation.status != "PASS"):
            raise StoreError("Validation evidence does not match this case, candidate and policy.")
        verdict = proposal.get("reviewer_verdict")
        if verdict is None or verdict.get("decision") != "ALLOW":
            raise StoreError("An allowing reviewer verdict is required.")

        record = ExecutionRecord(
            execution_id=f"exec_{uuid.uuid4().hex[:12]}",
            case_id=case_id,
            proposal_id=proposal_id,
            candidate_id=candidate_id,
            idempotency_key=idempotency_key,
            mode="SIMULATION",
            executed_at_utc=_now(),
        )
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO executions (execution_id, case_id, proposal_id,"
                    " candidate_id, idempotency_key, content_hash, mode, executed_at_utc)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (
                        record.execution_id,
                        record.case_id,
                        record.proposal_id,
                        record.candidate_id,
                        record.idempotency_key,
                        content_hash,
                        record.mode,
                        record.executed_at_utc,
                    ),
                )
                self._connection.execute(
                    "UPDATE proposals SET status = ? WHERE proposal_id = ?",
                    (PROPOSAL_EXECUTED, proposal_id),
                )
        except sqlite3.IntegrityError:
            # Lost a race; the winner's row is authoritative.
            row = self._connection.execute(
                "SELECT * FROM executions WHERE case_id = ? AND idempotency_key = ?",
                (case_id, idempotency_key),
            ).fetchone()
            if row is None:
                raise
            if row["content_hash"] != content_hash:
                raise IdempotencyConflict(
                    f"idempotency key {idempotency_key!r} was already used for a "
                    f"different proposal in this case"
                ) from None
            return self._execution_from_row(row), False

        return record, True

    @_synchronized
    def execution_for_case(self, case_id: str) -> ExecutionRecord | None:
        row = self._connection.execute(
            "SELECT * FROM executions WHERE case_id = ? ORDER BY executed_at_utc LIMIT 1",
            (case_id,),
        ).fetchone()
        return self._execution_from_row(row) if row is not None else None

    @staticmethod
    def _execution_from_row(row: sqlite3.Row) -> ExecutionRecord:
        return ExecutionRecord(
            execution_id=row["execution_id"],
            case_id=row["case_id"],
            proposal_id=row["proposal_id"],
            candidate_id=row["candidate_id"],
            idempotency_key=row["idempotency_key"],
            mode=row["mode"],
            executed_at_utc=row["executed_at_utc"],
        )
