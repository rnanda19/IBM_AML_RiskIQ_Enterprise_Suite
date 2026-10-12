"""SQLite-backed persistence for the casework package (RBAC/case-management phase,
2026-10-12). Closes the "No persistent store" gap `docs/architecture/INVESTIGATOR_WORKFLOW.md`
disclosed when `casework/` was first built: `Alert`/`CaseEvent`/`CaseNote`/`EvidenceReference`
were in-memory-only Pydantic objects with no way to survive a process restart.

Design, and why SQLite: this is a single-process-per-container deployment (same shape every
BP1-BP5 scoring service already has -- see `_security.py`'s own scope notes on in-process
metrics), so a real embedded database needs no separate server process, no new dependency
(sqlite3 is Python's standard library), and gives real ACID transactions -- a genuine
persistence layer, not a mock pretending to be one. HONEST SCOPE NOTE: a multi-process /
multi-replica deployment (e.g. `uvicorn --workers N`, or multiple container replicas behind a
load balancer) would need a real client-server database (Postgres, etc.) instead, since
SQLite's write-serialization is per-file, not cluster-aware -- not built here, disclosed
rather than silently inadequate.

Audit-trail protection against unauthorized modification (the explicit acceptance criterion
this phase was built against): two separate mechanisms, deliberately layered, not one claiming
to be the other:
  1. STRUCTURAL: `case_events`, `case_notes`, and `case_evidence` are APPEND-ONLY BY
     CONSTRUCTION -- this module contains no UPDATE or DELETE statement against any of the
     three, and the case-management REST API (`case_management_service.py`) exposes no route
     that could issue one. Only the single-row-per-alert `alerts` table (the CURRENT state --
     status/assigned_to/updated_at) is ever updated in place; the audit trail itself never is.
  2. CRYPTOGRAPHIC (tamper-EVIDENCE, not tamper-proofing): `case_lifecycle`'s hash chain over
     `case_events` means a row edited directly against the database (bypassing this module
     entirely, e.g. a manual `sqlite3` UPDATE) breaks `verify_integrity()`'s recomputation --
     see that function's own docstring for the exact (and honestly limited) guarantee.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from .alert_schema import Alert, CaseEvent, CaseNote, CaseStatus, EvidenceReference
from .case_lifecycle import (
    InvalidTransitionError,
)
from .case_lifecycle import add_evidence as _add_evidence
from .case_lifecycle import add_note as _add_note
from .case_lifecycle import assign as _assign
from .case_lifecycle import transition as _transition
from .case_lifecycle import verify_history_integrity
from .reconciliation import build_reconciliation_report

_SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    alert_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    entity_ref TEXT NOT NULL,
    transaction_ref TEXT,
    business_problem TEXT NOT NULL,
    detection_source TEXT NOT NULL,
    risk_score REAL NOT NULL,
    selected_threshold REAL NOT NULL,
    model_name TEXT NOT NULL,
    model_sha256 TEXT,
    dataset_variant TEXT,
    event_timestamp TEXT,
    scoring_timestamp TEXT NOT NULL,
    reason_codes TEXT NOT NULL,
    status TEXT NOT NULL,
    assigned_to TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    idempotency_key TEXT,
    severity TEXT,
    generation_source TEXT NOT NULL DEFAULT 'manual'
);
-- NOTE: the UNIQUE index on idempotency_key is created in _migrate_idempotency_columns()
-- below, not here -- a pre-existing "alerts" table (created before this phase, no
-- idempotency_key column yet) would make CREATE TABLE IF NOT EXISTS a no-op while this
-- index statement still runs unconditionally in the same executescript() batch, crashing
-- with "no such column" before the migration that would have added it ever gets to run.
-- Deferring the index creation to AFTER the migration step (which itself is `IF NOT
-- EXISTS`-safe and re-runs harmlessly on an already-migrated database) handles both a
-- brand-new database and a legacy one with the same code path.

-- Append-only: see module docstring's "STRUCTURAL" protection -- no code in this module
-- ever issues UPDATE/DELETE against this table.
CREATE TABLE IF NOT EXISTS case_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id TEXT NOT NULL REFERENCES alerts(alert_id),
    seq INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    actor TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    note TEXT,
    prev_event_hash TEXT,
    event_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_case_events_alert ON case_events(alert_id, seq);

-- Append-only: same protection as case_events above.
CREATE TABLE IF NOT EXISTS case_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id TEXT NOT NULL REFERENCES alerts(alert_id),
    note_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    actor TEXT NOT NULL,
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_case_notes_alert ON case_notes(alert_id);

-- Append-only: same protection as case_events above.
CREATE TABLE IF NOT EXISTS case_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id TEXT NOT NULL REFERENCES alerts(alert_id),
    evidence_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    actor TEXT NOT NULL,
    description TEXT NOT NULL,
    external_ref TEXT
);
CREATE INDEX IF NOT EXISTS idx_case_evidence_alert ON case_evidence(alert_id);
"""


class AlertNotFoundError(KeyError):
    """Raised when an alert_id does not exist in the store."""


class AlertStore:
    """One AlertStore per database file. Each public method opens its own short-lived
    connection (rather than holding one open across calls/threads) -- simple and correct under
    a multi-threaded ASGI server without needing `check_same_thread=False` tricks; SQLite's
    own file-level locking serializes concurrent writers. A process-wide lock additionally
    serializes this module's own write methods so a read-modify-write sequence (e.g.
    apply_transition's load-then-update) cannot race with itself across threads in the same
    process -- SQLite's file locking alone handles cross-process safety, this lock handles the
    same-process compound-operation case."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            self._migrate_idempotency_columns(conn)

    def _migrate_idempotency_columns(self, conn: sqlite3.Connection) -> None:
        """`CREATE TABLE IF NOT EXISTS` (above) does not retroactively add columns to a
        table that already existed on disk before this phase (idempotency_key/severity/
        generation_source, added 2026-10-12) -- a real deployment's pre-existing
        data/case_management/casework.db would otherwise be stuck on the old schema
        forever. Cheap, idempotent, and safe to run on every startup: checks the real
        column list via PRAGMA table_info and ALTER TABLE ADD COLUMN only for whatever is
        actually missing (a brand-new database created fresh by _SCHEMA above already has
        all three, so this is a silent no-op there)."""
        existing = {row[1] for row in conn.execute("PRAGMA table_info(alerts)").fetchall()}
        if "idempotency_key" not in existing:
            conn.execute("ALTER TABLE alerts ADD COLUMN idempotency_key TEXT")
        if "severity" not in existing:
            conn.execute("ALTER TABLE alerts ADD COLUMN severity TEXT")
        if "generation_source" not in existing:
            conn.execute("ALTER TABLE alerts ADD COLUMN generation_source TEXT NOT NULL DEFAULT 'manual'")
        # The partial unique index itself is also `IF NOT EXISTS` and column-order-
        # independent, so it is safe (and necessary, for a pre-existing DB) to re-run here.
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_alerts_idempotency_key "
            "ON alerts(idempotency_key) WHERE idempotency_key IS NOT NULL"
        )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # -- internal: row <-> model reconstruction ------------------------------------------

    def _load_events(self, conn: sqlite3.Connection, alert_id: str) -> list[CaseEvent]:
        rows = conn.execute(
            "SELECT * FROM case_events WHERE alert_id = ? ORDER BY seq ASC", (alert_id,)
        ).fetchall()
        return [
            CaseEvent(
                timestamp=datetime.fromisoformat(r["timestamp"]),
                actor=r["actor"],
                from_status=CaseStatus(r["from_status"]) if r["from_status"] else None,
                to_status=CaseStatus(r["to_status"]),
                note=r["note"],
                prev_event_hash=r["prev_event_hash"],
                event_hash=r["event_hash"],
            )
            for r in rows
        ]

    def _load_notes(self, conn: sqlite3.Connection, alert_id: str) -> list[CaseNote]:
        rows = conn.execute(
            "SELECT * FROM case_notes WHERE alert_id = ? ORDER BY id ASC", (alert_id,)
        ).fetchall()
        return [
            CaseNote(
                note_id=r["note_id"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
                actor=r["actor"],
                text=r["text"],
            )
            for r in rows
        ]

    def _load_evidence(self, conn: sqlite3.Connection, alert_id: str) -> list[EvidenceReference]:
        rows = conn.execute(
            "SELECT * FROM case_evidence WHERE alert_id = ? ORDER BY id ASC", (alert_id,)
        ).fetchall()
        return [
            EvidenceReference(
                evidence_id=r["evidence_id"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
                actor=r["actor"],
                description=r["description"],
                external_ref=r["external_ref"],
            )
            for r in rows
        ]

    def _row_to_alert(self, conn: sqlite3.Connection, row: sqlite3.Row) -> Alert:
        row_keys = row.keys()
        return Alert(
            schema_version=row["schema_version"],
            alert_id=row["alert_id"],
            entity_ref=row["entity_ref"],
            transaction_ref=row["transaction_ref"],
            business_problem=row["business_problem"],
            detection_source=row["detection_source"],
            risk_score=row["risk_score"],
            selected_threshold=row["selected_threshold"],
            model_name=row["model_name"],
            model_sha256=row["model_sha256"],
            dataset_variant=row["dataset_variant"],
            event_timestamp=(
                datetime.fromisoformat(row["event_timestamp"]) if row["event_timestamp"] else None
            ),
            scoring_timestamp=datetime.fromisoformat(row["scoring_timestamp"]),
            reason_codes=json.loads(row["reason_codes"]),
            status=CaseStatus(row["status"]),
            assigned_to=row["assigned_to"],
            history=self._load_events(conn, row["alert_id"]),
            notes=self._load_notes(conn, row["alert_id"]),
            evidence=self._load_evidence(conn, row["alert_id"]),
            # row_keys guard: a row fetched mid-migration (between executescript() and
            # _migrate_idempotency_columns() in the same __init__ call) could theoretically
            # lack these columns; in practice __init__ always finishes migrating before any
            # query runs, so this is defensive, not load-bearing.
            idempotency_key=row["idempotency_key"] if "idempotency_key" in row_keys else None,
            severity=row["severity"] if "severity" in row_keys else None,
            generation_source=row["generation_source"] if "generation_source" in row_keys else "manual",
        )

    def _insert_alert_row(self, conn: sqlite3.Connection, alert: Alert, *, now: str) -> None:
        conn.execute(
            """INSERT INTO alerts (
                alert_id, schema_version, entity_ref, transaction_ref, business_problem,
                detection_source, risk_score, selected_threshold, model_name, model_sha256,
                dataset_variant, event_timestamp, scoring_timestamp, reason_codes, status,
                assigned_to, created_at, updated_at, idempotency_key, severity,
                generation_source
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                alert.alert_id,
                alert.schema_version,
                alert.entity_ref,
                alert.transaction_ref,
                alert.business_problem,
                alert.detection_source,
                alert.risk_score,
                alert.selected_threshold,
                alert.model_name,
                alert.model_sha256,
                alert.dataset_variant,
                alert.event_timestamp.isoformat() if alert.event_timestamp else None,
                alert.scoring_timestamp.isoformat(),
                json.dumps(alert.reason_codes),
                alert.status.value,
                alert.assigned_to,
                now,
                now,
                alert.idempotency_key,
                alert.severity,
                alert.generation_source,
            ),
        )

    def _append_event_row(self, conn: sqlite3.Connection, alert_id: str, event: CaseEvent) -> None:
        seq = conn.execute(
            "SELECT COALESCE(MAX(seq), -1) + 1 FROM case_events WHERE alert_id = ?", (alert_id,)
        ).fetchone()[0]
        conn.execute(
            """INSERT INTO case_events
               (alert_id, seq, timestamp, actor, from_status, to_status, note, prev_event_hash, event_hash)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                alert_id,
                seq,
                event.timestamp.isoformat(),
                event.actor,
                event.from_status.value if event.from_status else None,
                event.to_status.value,
                event.note,
                event.prev_event_hash,
                event.event_hash,
            ),
        )

    # -- public API -----------------------------------------------------------------------

    def create_alert(self, alert: Alert) -> Alert:
        """Persists a brand-new Alert (status/history/notes/evidence as given -- normally
        CaseStatus.NEW with empty history, but not enforced here so a caller migrating
        already-in-flight alerts from another source is not blocked)."""
        now = datetime.now(alert.scoring_timestamp.tzinfo or None).isoformat()
        with self._write_lock, self._connect() as conn:
            self._insert_alert_row(conn, alert, now=now)
            for event in alert.history:
                self._append_event_row(conn, alert.alert_id, event)
            for note in alert.notes:
                conn.execute(
                    "INSERT INTO case_notes (alert_id, note_id, timestamp, actor, text) VALUES (?,?,?,?,?)",
                    (alert.alert_id, note.note_id, note.timestamp.isoformat(), note.actor, note.text),
                )
            for ref in alert.evidence:
                conn.execute(
                    "INSERT INTO case_evidence "
                    "(alert_id, evidence_id, timestamp, actor, description, external_ref) "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        alert.alert_id,
                        ref.evidence_id,
                        ref.timestamp.isoformat(),
                        ref.actor,
                        ref.description,
                        ref.external_ref,
                    ),
                )
        return alert

    def get_alert(self, alert_id: str) -> Alert:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM alerts WHERE alert_id = ?", (alert_id,)).fetchone()
            if row is None:
                raise AlertNotFoundError(alert_id)
            return self._row_to_alert(conn, row)

    def get_alert_by_idempotency_key(self, idempotency_key: str) -> Alert | None:
        """Returns the alert already stored under this idempotency_key, or None if no such
        alert exists yet. Used both by create_alert_idempotent() (the race-safe path, which
        does not rely on this method alone -- see its own docstring) and by a caller that
        wants to check for a prior delivery without attempting a write."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM alerts WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            return self._row_to_alert(conn, row) if row is not None else None

    def create_alert_idempotent(self, alert: Alert) -> tuple[Alert, bool]:
        """Idempotent alert creation keyed on alert.idempotency_key -- the real enforcement
        behind "retries do not create duplicate alerts". Returns (alert, True) if this call
        created a brand-new row, or (the ALREADY-STORED alert, False) if one with the same
        idempotency_key already existed -- the caller gets back the real persisted alert
        either way, never a value it has to reconcile itself.

        Race-safety, not just a check-then-insert: the UNIQUE index on idempotency_key (see
        _SCHEMA) is the actual source of truth. This method attempts the INSERT directly and
        only falls back to a SELECT if that insert fails with an IntegrityError that is
        specifically the idempotency_key conflict (detected by string-matching the real
        sqlite3 error message, which names the failing index/column) -- any OTHER
        IntegrityError (e.g. a genuine alert_id collision, which create_alert() already
        tests raises) is re-raised unchanged, never silently swallowed as "it must have been
        a duplicate". Two concurrent callers racing to create the same idempotency_key both
        attempt the INSERT; SQLite's own file-level locking (serialized further by this
        store's own _write_lock for same-process callers) means at most one can win, and the
        loser's IntegrityError is exactly what routes it to the re-fetch-and-return-existing
        path -- correct under real concurrency, not just the common case.

        If alert.idempotency_key is None (a manually created alert, or a caller that chose
        not to deduplicate), this is simply create_alert() -- always creates, as before."""
        if alert.idempotency_key is None:
            self.create_alert(alert)
            return alert, True
        now = datetime.now(alert.scoring_timestamp.tzinfo or None).isoformat()
        with self._write_lock, self._connect() as conn:
            try:
                self._insert_alert_row(conn, alert, now=now)
            except sqlite3.IntegrityError as exc:
                if "idempotency_key" not in str(exc):
                    raise
                row = conn.execute(
                    "SELECT * FROM alerts WHERE idempotency_key = ?", (alert.idempotency_key,)
                ).fetchone()
                if row is None:
                    raise  # genuinely unexpected -- do not mask an error we cannot explain
                return self._row_to_alert(conn, row), False
            for event in alert.history:
                self._append_event_row(conn, alert.alert_id, event)
            for note in alert.notes:
                conn.execute(
                    "INSERT INTO case_notes (alert_id, note_id, timestamp, actor, text) VALUES (?,?,?,?,?)",
                    (alert.alert_id, note.note_id, note.timestamp.isoformat(), note.actor, note.text),
                )
            for ref in alert.evidence:
                conn.execute(
                    "INSERT INTO case_evidence "
                    "(alert_id, evidence_id, timestamp, actor, description, external_ref) "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        alert.alert_id,
                        ref.evidence_id,
                        ref.timestamp.isoformat(),
                        ref.actor,
                        ref.description,
                        ref.external_ref,
                    ),
                )
            return alert, True

    def count_unresolved(self) -> int:
        """A live COUNT of every alert not yet in a terminal state (everything except
        CLOSED) -- the "unresolved alerts" observability gauge requirement. A single SQL
        COUNT, not a Python-side len(list_alerts(...)) over every row's full history/notes/
        evidence (list_alerts reconstructs full Alert objects via _row_to_alert, real but
        unnecessary work for a count this cheap to compute directly)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM alerts WHERE status != ?", (CaseStatus.CLOSED.value,)
            ).fetchone()
            return int(row[0])

    def list_alerts(
        self,
        *,
        status: CaseStatus | None = None,
        business_problem: str | None = None,
        assigned_to: str | None = None,
        entity_ref: str | None = None,
        limit: int = 200,
    ) -> list[Alert]:
        clauses, params = [], []
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        if business_problem is not None:
            clauses.append("business_problem = ?")
            params.append(business_problem)
        if assigned_to is not None:
            clauses.append("assigned_to = ?")
            params.append(assigned_to)
        if entity_ref is not None:
            clauses.append("entity_ref = ?")
            params.append(entity_ref)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            # `where` is built only from the fixed literal strings above ("status = ?",
            # "business_problem = ?", ...), never from a caller-supplied value; every real
            # value (status/business_problem/assigned_to/entity_ref/limit) is passed through
            # the parameterized `?` placeholders in `params`, not interpolated into the SQL
            # text. bandit's B608 pattern-matches any f-string used to build a query string
            # regardless of whether the interpolated part is attacker-controlled -- confirmed
            # false positive here, same resolution this project already uses for its
            # # nosec B301 pickle.load findings.
            rows = conn.execute(
                f"SELECT * FROM alerts {where} ORDER BY scoring_timestamp DESC LIMIT ?",  # nosec B608
                (*params, limit),
            ).fetchall()
            return [self._row_to_alert(conn, r) for r in rows]

    def apply_transition(
        self, alert_id: str, to_status: CaseStatus, *, actor: str, note: str | None = None
    ) -> Alert:
        """Loads the current alert, computes the new state via case_lifecycle.transition()
        (which raises InvalidTransitionError for a disallowed move -- propagated, not
        swallowed), then persists the status change and the one new CaseEvent atomically."""
        with self._write_lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM alerts WHERE alert_id = ?", (alert_id,)).fetchone()
            if row is None:
                raise AlertNotFoundError(alert_id)
            current = self._row_to_alert(conn, row)
            updated = _transition(current, to_status, actor=actor, note=note)
            now = datetime.now().isoformat()
            conn.execute(
                "UPDATE alerts SET status = ?, updated_at = ? WHERE alert_id = ?",
                (updated.status.value, now, alert_id),
            )
            self._append_event_row(conn, alert_id, updated.history[-1])
            return updated

    def assign(self, alert_id: str, *, assignee: str, actor: str, note: str | None = None) -> Alert:
        with self._write_lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM alerts WHERE alert_id = ?", (alert_id,)).fetchone()
            if row is None:
                raise AlertNotFoundError(alert_id)
            current = self._row_to_alert(conn, row)
            updated = _assign(current, assignee=assignee, actor=actor, note=note)
            now = datetime.now().isoformat()
            conn.execute(
                "UPDATE alerts SET status = ?, assigned_to = ?, updated_at = ? WHERE alert_id = ?",
                (updated.status.value, updated.assigned_to, now, alert_id),
            )
            if len(updated.history) > len(current.history):
                self._append_event_row(conn, alert_id, updated.history[-1])
            return updated

    def add_note(self, alert_id: str, *, actor: str, text: str) -> Alert:
        with self._write_lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM alerts WHERE alert_id = ?", (alert_id,)).fetchone()
            if row is None:
                raise AlertNotFoundError(alert_id)
            current = self._row_to_alert(conn, row)
            updated = _add_note(current, actor=actor, text=text)
            new_note = updated.notes[-1]
            conn.execute(
                "INSERT INTO case_notes (alert_id, note_id, timestamp, actor, text) VALUES (?,?,?,?,?)",
                (alert_id, new_note.note_id, new_note.timestamp.isoformat(), new_note.actor, new_note.text),
            )
            conn.execute(
                "UPDATE alerts SET updated_at = ? WHERE alert_id = ?", (datetime.now().isoformat(), alert_id)
            )
            return updated

    def add_evidence(
        self, alert_id: str, *, actor: str, description: str, external_ref: str | None = None
    ) -> Alert:
        with self._write_lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM alerts WHERE alert_id = ?", (alert_id,)).fetchone()
            if row is None:
                raise AlertNotFoundError(alert_id)
            current = self._row_to_alert(conn, row)
            updated = _add_evidence(current, actor=actor, description=description, external_ref=external_ref)
            new_ref = updated.evidence[-1]
            conn.execute(
                "INSERT INTO case_evidence "
                "(alert_id, evidence_id, timestamp, actor, description, external_ref) "
                "VALUES (?,?,?,?,?,?)",
                (
                    alert_id,
                    new_ref.evidence_id,
                    new_ref.timestamp.isoformat(),
                    new_ref.actor,
                    new_ref.description,
                    new_ref.external_ref,
                ),
            )
            conn.execute(
                "UPDATE alerts SET updated_at = ? WHERE alert_id = ?", (datetime.now().isoformat(), alert_id)
            )
            return updated

    def verify_integrity(self, alert_id: str) -> dict:
        """Reloads the alert's history fresh from the database (never from an in-memory
        cache) and recomputes the hash chain -- see verify_history_integrity()'s own
        docstring for the exact guarantee this does and does not make."""
        alert = self.get_alert(alert_id)
        verified, reason = verify_history_integrity(alert)
        return {
            "alert_id": alert_id,
            "verified": verified,
            "reason": reason,
            "checked_events": len(alert.history),
        }

    def reconciliation_report(
        self,
        *,
        n_transactions_evaluated: int,
        n_rejected: int = 0,
        window_hours: float = 24.0,
        business_problem: str | None = None,
    ) -> dict:
        alerts = self.list_alerts(business_problem=business_problem, limit=10_000)
        return build_reconciliation_report(
            alerts,
            n_transactions_evaluated=n_transactions_evaluated,
            n_rejected=n_rejected,
            window_hours=window_hours,
        )


__all__ = ["AlertStore", "AlertNotFoundError", "InvalidTransitionError"]
