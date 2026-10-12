"""Tests for src/aml_riskiq/casework/store.py -- the SQLite-backed persistence layer added in
the RBAC/case-management phase (2026-10-12). Scope: this file tests the STORE's own logic
(CRUD, the append-only guarantee, hash-chain integrity surviving a real restart, reconciliation
over persisted alerts) against a real temporary SQLite database file -- not a mock. RBAC/route
enforcement is a separate concern, tested in
tests/integration/case_management/test_case_management_service.py."""

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_src_path = str(Path(__file__).resolve().parents[2] / "src" / "aml_riskiq")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

from casework.alert_schema import Alert, CaseStatus  # noqa: E402
from casework.case_lifecycle import InvalidTransitionError  # noqa: E402
from casework.store import AlertNotFoundError, AlertStore  # noqa: E402

NOW = datetime(2026, 10, 12, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def store(tmp_path):
    return AlertStore(tmp_path / "casework_test.db")


def _alert(**overrides) -> Alert:
    defaults = dict(
        entity_ref="acct-001",
        business_problem="BP1",
        detection_source="xgboost_champion",
        risk_score=0.87,
        selected_threshold=0.5,
        model_name="xgboost_v1",
        scoring_timestamp=NOW,
    )
    defaults.update(overrides)
    return Alert(**defaults)


# -- create / get -----------------------------------------------------------------------------


def test_create_and_get_alert_round_trips(store):
    a = _alert()
    store.create_alert(a)
    loaded = store.get_alert(a.alert_id)
    assert loaded.alert_id == a.alert_id
    assert loaded.entity_ref == "acct-001"
    assert loaded.business_problem == "BP1"
    assert loaded.risk_score == 0.87
    assert loaded.status == CaseStatus.NEW
    assert loaded.history == []
    assert loaded.notes == []
    assert loaded.evidence == []


def test_get_nonexistent_alert_raises(store):
    with pytest.raises(AlertNotFoundError):
        store.get_alert("does-not-exist")


def test_create_duplicate_alert_id_raises(store):
    a = _alert()
    store.create_alert(a)
    with pytest.raises(sqlite3.IntegrityError):
        store.create_alert(a)


def test_db_file_actually_created_on_disk(tmp_path):
    db_path = tmp_path / "subdir" / "casework.db"
    AlertStore(db_path)
    assert db_path.exists()


# -- list_alerts --------------------------------------------------------------------------------


def test_list_alerts_filters_by_status(store):
    a1 = _alert(entity_ref="acct-1")
    a2 = _alert(entity_ref="acct-2")
    store.create_alert(a1)
    store.create_alert(a2)
    store.apply_transition(a1.alert_id, CaseStatus.ASSIGNED, actor="x")
    new_only = store.list_alerts(status=CaseStatus.NEW)
    assert len(new_only) == 1
    assert new_only[0].alert_id == a2.alert_id


def test_list_alerts_filters_by_business_problem(store):
    store.create_alert(_alert(entity_ref="acct-1", business_problem="BP1"))
    store.create_alert(_alert(entity_ref="acct-2", business_problem="BP4"))
    bp4_only = store.list_alerts(business_problem="BP4")
    assert len(bp4_only) == 1
    assert bp4_only[0].business_problem == "BP4"


def test_list_alerts_filters_by_assigned_to(store):
    a1 = _alert(entity_ref="acct-1")
    store.create_alert(a1)
    store.assign(a1.alert_id, assignee="inv-1", actor="supervisor")
    store.create_alert(_alert(entity_ref="acct-2"))
    mine = store.list_alerts(assigned_to="inv-1")
    assert len(mine) == 1
    assert mine[0].entity_ref == "acct-1"


# -- apply_transition --------------------------------------------------------------------------


def test_apply_transition_persists_status_and_event(store):
    a = _alert()
    store.create_alert(a)
    updated = store.apply_transition(a.alert_id, CaseStatus.ASSIGNED, actor="inv-1", note="picked up")
    assert updated.status == CaseStatus.ASSIGNED
    reloaded = store.get_alert(a.alert_id)
    assert reloaded.status == CaseStatus.ASSIGNED
    assert len(reloaded.history) == 1
    assert reloaded.history[0].actor == "inv-1"
    assert reloaded.history[0].note == "picked up"


def test_apply_transition_invalid_raises_and_does_not_persist(store):
    a = _alert()
    store.create_alert(a)
    with pytest.raises(InvalidTransitionError):
        store.apply_transition(a.alert_id, CaseStatus.ESCALATED, actor="x")  # NEW -> ESCALATED not allowed
    reloaded = store.get_alert(a.alert_id)
    assert reloaded.status == CaseStatus.NEW  # unchanged
    assert reloaded.history == []


def test_apply_transition_nonexistent_alert_raises(store):
    with pytest.raises(AlertNotFoundError):
        store.apply_transition("ghost", CaseStatus.ASSIGNED, actor="x")


def test_multiple_transitions_build_a_hash_chain_that_survives_reload(store):
    a = _alert()
    store.create_alert(a)
    store.apply_transition(a.alert_id, CaseStatus.ASSIGNED, actor="x")
    store.apply_transition(a.alert_id, CaseStatus.UNDER_REVIEW, actor="y")
    store.apply_transition(a.alert_id, CaseStatus.CLOSED, actor="z")
    reloaded = store.get_alert(a.alert_id)
    assert len(reloaded.history) == 3
    assert reloaded.history[0].prev_event_hash is None
    assert reloaded.history[1].prev_event_hash == reloaded.history[0].event_hash
    assert reloaded.history[2].prev_event_hash == reloaded.history[1].event_hash
    result = store.verify_integrity(a.alert_id)
    assert result["verified"] is True
    assert result["checked_events"] == 3


# -- assign ---------------------------------------------------------------------------------


def test_assign_new_alert_sets_status_and_owner(store):
    a = _alert()
    store.create_alert(a)
    updated = store.assign(a.alert_id, assignee="inv-1", actor="supervisor")
    assert updated.status == CaseStatus.ASSIGNED
    assert updated.assigned_to == "inv-1"
    reloaded = store.get_alert(a.alert_id)
    assert reloaded.assigned_to == "inv-1"
    assert len(reloaded.history) == 1


def test_reassign_already_working_case_does_not_add_history_event(store):
    a = _alert()
    store.create_alert(a)
    store.assign(a.alert_id, assignee="inv-1", actor="supervisor")  # NEW -> ASSIGNED, 1 event
    store.apply_transition(a.alert_id, CaseStatus.UNDER_REVIEW, actor="inv-1")  # 2 events
    store.assign(a.alert_id, assignee="inv-2", actor="supervisor")  # reassignment only
    reloaded = store.get_alert(a.alert_id)
    assert reloaded.assigned_to == "inv-2"
    assert reloaded.status == CaseStatus.UNDER_REVIEW  # unchanged by the reassignment
    assert len(reloaded.history) == 2  # no 3rd event from the pure reassignment


# -- notes / evidence -------------------------------------------------------------------------


def test_add_note_persists_and_reloads(store):
    a = _alert()
    store.create_alert(a)
    store.add_note(a.alert_id, actor="inv-1", text="reviewed transaction history")
    reloaded = store.get_alert(a.alert_id)
    assert len(reloaded.notes) == 1
    assert reloaded.notes[0].text == "reviewed transaction history"
    assert reloaded.notes[0].actor == "inv-1"
    assert reloaded.status == CaseStatus.NEW  # a note never changes status


def test_add_evidence_persists_and_reloads(store):
    a = _alert()
    store.create_alert(a)
    store.add_evidence(a.alert_id, actor="inv-1", description="wire confirmation", external_ref="wire://abc")
    reloaded = store.get_alert(a.alert_id)
    assert len(reloaded.evidence) == 1
    assert reloaded.evidence[0].description == "wire confirmation"
    assert reloaded.evidence[0].external_ref == "wire://abc"


def test_multiple_notes_preserve_insertion_order(store):
    a = _alert()
    store.create_alert(a)
    store.add_note(a.alert_id, actor="inv-1", text="first")
    store.add_note(a.alert_id, actor="inv-1", text="second")
    reloaded = store.get_alert(a.alert_id)
    assert [n.text for n in reloaded.notes] == ["first", "second"]


# -- append-only guarantee (structural protection, see store.py module docstring) -------------


def test_case_events_table_has_no_update_or_delete_in_store_module():
    """A structural guarantee check -- confirms the store module's OWN source never issues an
    UPDATE or DELETE against case_events/case_notes/case_evidence (the audit-protection
    mechanism this phase's acceptance criterion asked for). Regexes the module's source
    rather than inspecting SQL at runtime, since the guarantee is "this code never does X",
    which a runtime test can't prove the absence of as directly as reading the source can."""
    import re

    source = (Path(_src_path) / "casework" / "store.py").read_text(encoding="utf-8")
    for table in ("case_events", "case_notes", "case_evidence"):
        assert not re.search(
            rf"UPDATE\s+{table}\b", source, re.IGNORECASE
        ), f"found an UPDATE against {table}"
        assert not re.search(
            rf"DELETE\s+FROM\s+{table}\b", source, re.IGNORECASE
        ), f"found a DELETE against {table}"


def test_tampering_with_raw_db_row_is_detected_on_reload(store):
    """Simulates an out-of-band edit bypassing this module entirely (e.g. a DBA/attacker
    running raw SQL against the file) -- verify_integrity() must catch it on the next read."""
    a = _alert()
    store.create_alert(a)
    store.apply_transition(a.alert_id, CaseStatus.ASSIGNED, actor="inv-1", note="original")

    conn = sqlite3.connect(store.db_path)
    conn.execute("UPDATE case_events SET note = 'TAMPERED' WHERE alert_id = ?", (a.alert_id,))
    conn.commit()
    conn.close()

    result = store.verify_integrity(a.alert_id)
    assert result["verified"] is False
    assert "event_hash" in result["reason"]


# -- reconciliation ---------------------------------------------------------------------------


def test_reconciliation_report_over_persisted_alerts(store):
    store.create_alert(_alert(entity_ref="acct-1"))
    a2 = _alert(entity_ref="acct-2")
    store.create_alert(a2)
    store.apply_transition(a2.alert_id, CaseStatus.ASSIGNED, actor="x")
    report = store.reconciliation_report(n_transactions_evaluated=5000, n_rejected=2)
    assert report["n_transactions_evaluated"] == 5000
    assert report["n_rejected"] == 2
    assert report["n_alerts_generated"] == 2
    assert report["status_counts"]["new"] == 1
    assert report["status_counts"]["assigned"] == 1


def test_reconciliation_report_filters_by_business_problem(store):
    store.create_alert(_alert(entity_ref="acct-1", business_problem="BP1"))
    store.create_alert(_alert(entity_ref="acct-2", business_problem="BP4"))
    report = store.reconciliation_report(n_transactions_evaluated=100, business_problem="BP1")
    assert report["n_alerts_generated"] == 1


# -- idempotent alert creation (end-to-end AML workflow integration phase, 2026-10-12) ---------


def test_create_alert_idempotent_first_call_creates(store):
    a = _alert(entity_ref="acct-idem-1")
    a = a.model_copy(update={"idempotency_key": "key-1"})
    created, was_new = store.create_alert_idempotent(a)
    assert was_new is True
    assert created.alert_id == a.alert_id
    reloaded = store.get_alert(a.alert_id)
    assert reloaded.idempotency_key == "key-1"


def test_create_alert_idempotent_second_call_returns_existing_not_duplicate(store):
    a1 = _alert(entity_ref="acct-idem-2").model_copy(update={"idempotency_key": "key-2"})
    a2 = _alert(entity_ref="acct-idem-2").model_copy(update={"idempotency_key": "key-2"})
    first, was_new_1 = store.create_alert_idempotent(a1)
    second, was_new_2 = store.create_alert_idempotent(a2)
    assert was_new_1 is True
    assert was_new_2 is False
    assert second.alert_id == first.alert_id  # same real stored alert, not a2's own id
    all_alerts = store.list_alerts(entity_ref="acct-idem-2")
    assert len(all_alerts) == 1  # never two rows for the same idempotency_key


def test_create_alert_idempotent_without_key_always_creates(store):
    """A manually created alert (idempotency_key=None) is never deduplicated -- two
    separate manual submissions are two separate real alerts, same as create_alert()."""
    a1 = _alert(entity_ref="acct-manual")
    a2 = _alert(entity_ref="acct-manual")
    _, new1 = store.create_alert_idempotent(a1)
    _, new2 = store.create_alert_idempotent(a2)
    assert new1 is True
    assert new2 is True
    assert len(store.list_alerts(entity_ref="acct-manual")) == 2


def test_create_alert_idempotent_different_keys_both_created(store):
    a1 = _alert(entity_ref="acct-idem-3").model_copy(update={"idempotency_key": "key-a"})
    a2 = _alert(entity_ref="acct-idem-3").model_copy(update={"idempotency_key": "key-b"})
    _, new1 = store.create_alert_idempotent(a1)
    _, new2 = store.create_alert_idempotent(a2)
    assert new1 is True
    assert new2 is True
    assert len(store.list_alerts(entity_ref="acct-idem-3")) == 2


def test_create_alert_idempotent_preserves_severity_and_generation_source(store):
    a = _alert(entity_ref="acct-idem-4").model_copy(
        update={
            "idempotency_key": "key-sev",
            "severity": "critical",
            "generation_source": "automated_scoring",
        }
    )
    store.create_alert_idempotent(a)
    reloaded = store.get_alert(a.alert_id)
    assert reloaded.severity == "critical"
    assert reloaded.generation_source == "automated_scoring"


def test_get_alert_by_idempotency_key_found_and_not_found(store):
    a = _alert(entity_ref="acct-idem-5").model_copy(update={"idempotency_key": "key-lookup"})
    store.create_alert_idempotent(a)
    found = store.get_alert_by_idempotency_key("key-lookup")
    assert found is not None
    assert found.alert_id == a.alert_id
    assert store.get_alert_by_idempotency_key("no-such-key") is None


def test_manually_created_alert_has_manual_generation_source_by_default(store):
    a = _alert(entity_ref="acct-manual-default")
    store.create_alert(a)
    reloaded = store.get_alert(a.alert_id)
    assert reloaded.generation_source == "manual"
    assert reloaded.idempotency_key is None
    assert reloaded.severity is None


# -- count_unresolved ---------------------------------------------------------------------------


def test_count_unresolved_excludes_closed_only(store):
    a1 = _alert(entity_ref="acct-u1")
    a2 = _alert(entity_ref="acct-u2")
    a3 = _alert(entity_ref="acct-u3")
    store.create_alert(a1)
    store.create_alert(a2)
    store.create_alert(a3)
    store.apply_transition(a1.alert_id, CaseStatus.ASSIGNED, actor="x")
    store.apply_transition(a2.alert_id, CaseStatus.ASSIGNED, actor="x")
    store.apply_transition(a2.alert_id, CaseStatus.UNDER_REVIEW, actor="x")
    store.apply_transition(a2.alert_id, CaseStatus.CLOSED, actor="x")
    # a1: ASSIGNED (unresolved), a2: CLOSED (resolved), a3: NEW (unresolved)
    assert store.count_unresolved() == 2


def test_count_unresolved_zero_on_empty_store(store):
    assert store.count_unresolved() == 0


# -- schema migration for a pre-existing database (idempotency columns added 2026-10-12) -------


def test_migration_adds_idempotency_columns_to_pre_existing_db(tmp_path):
    """Simulates a real on-disk casework.db created BEFORE this phase (no idempotency_key/
    severity/generation_source columns) -- opening it with the current AlertStore must
    migrate it in place, not crash or silently ignore the old rows."""
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE alerts (
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
            updated_at TEXT NOT NULL
        );
        """)
    conn.execute(
        "INSERT INTO alerts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "legacy-alert-1",
            "1.0.0",
            "acct-legacy",
            None,
            "BP1",
            "xgboost_champion",
            0.9,
            0.5,
            "XGBoost",
            None,
            None,
            None,
            NOW.isoformat(),
            "[]",
            "new",
            None,
            NOW.isoformat(),
            NOW.isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    store = AlertStore(db_path)  # must not raise -- migrates the pre-existing table in place
    reloaded = store.get_alert("legacy-alert-1")
    assert reloaded.entity_ref == "acct-legacy"
    assert reloaded.idempotency_key is None
    assert reloaded.severity is None
    assert reloaded.generation_source == "manual"

    # And the new store is fully functional on the migrated table, including idempotency.
    new_alert = _alert(entity_ref="acct-post-migration").model_copy(update={"idempotency_key": "post-key"})
    store.create_alert_idempotent(new_alert)
    assert store.get_alert_by_idempotency_key("post-key") is not None


# -- resilience: restart recovery + interrupted-write atomicity (Improvement 3
# production-readiness pass, 2026-10-12) -- see docs/operations/RESILIENCE_TEST_PLAN.md --------


def test_data_survives_a_fresh_store_instance_against_the_same_db_file(tmp_path):
    """Simulates a real service restart (a container/process stopping and a new one starting
    against the same persistent volume) WITHOUT needing a live Docker daemon: a second,
    completely independent AlertStore object -- no shared Python state, no shared connection
    -- opened against the same on-disk SQLite file as the first, after the first store object
    is discarded. SQLite's own durability (each write commits before _connect() returns) is
    what real restart recovery depends on in this architecture; this test exercises that real
    guarantee rather than asserting it from the docstring."""
    from casework.store import AlertStore as _AlertStoreCls

    db_path = tmp_path / "restart_test.db"
    store1 = _AlertStoreCls(db_path)
    alert = _alert(entity_ref="restart-acct")
    store1.create_alert(alert)
    store1.assign(alert.alert_id, assignee="investigator-1", actor="admin")
    store1.add_note(alert.alert_id, actor="investigator-1", text="working this case")
    del store1  # as close a Python-level stand-in for "the old process is gone" as this gets

    store2 = _AlertStoreCls(db_path)  # a fresh instance, as a newly-started process would create
    reloaded = store2.get_alert(alert.alert_id)
    assert reloaded.assigned_to == "investigator-1"
    assert len(reloaded.notes) == 1
    assert reloaded.notes[0].text == "working this case"
    assert len(reloaded.history) == 1  # the assign() transition's own appended event
    integrity = store2.verify_integrity(alert.alert_id)
    assert integrity["verified"] is True  # hash chain still verifies after the "restart"


def test_create_alert_rolls_back_fully_when_interrupted_partway_through(store, monkeypatch):
    """Simulates an interrupted write (a crash, or any exception) partway through
    create_alert()'s real multi-statement transaction (alert row, then N history-event rows,
    then notes, then evidence -- all one SQLite transaction, see store.py's own _connect()).
    Confirms the real, existing atomicity guarantee (commit only at the very end; any
    exception rolls back everything) rather than assuming it: after the first of two history
    events is appended but the second raises, NEITHER the alert row NOR the first event
    should be left behind -- a half-written case is strictly worse than a rejected one."""
    from casework.case_lifecycle import transition

    alert = _alert(entity_ref="interrupted-acct")
    alert = transition(alert, CaseStatus.ASSIGNED, actor="admin", now=NOW)
    alert = transition(alert, CaseStatus.UNDER_REVIEW, actor="investigator-1", now=NOW)
    assert len(alert.history) == 2  # two real, hash-chained events built entirely in memory

    # Patched on type(store) -- the fixture's OWN actual class -- rather than via a fresh
    # `import casework.store`, which could resolve to a different module object than the
    # fixture's instance if another test file in the same pytest session has reloaded
    # casework.store via sys.modules.pop() (several integration test files do this for their
    # own fixture isolation) in between collection and this test running. Patching
    # type(store) directly is immune to that -- it is always the exact class whose
    # create_alert() this test calls.
    call_count = {"n": 0}
    real_append = type(store)._append_event_row

    def _flaky_append(self, conn, alert_id, event):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated crash mid-write (e.g. disk full, process killed)")
        return real_append(self, conn, alert_id, event)

    monkeypatch.setattr(type(store), "_append_event_row", _flaky_append)

    with pytest.raises(RuntimeError, match="simulated crash"):
        store.create_alert(alert)

    assert call_count["n"] == 2  # confirms the failure actually happened mid-transaction,
    # not before create_alert even started inserting
    with pytest.raises(AlertNotFoundError):
        store.get_alert(alert.alert_id)  # the alert row itself must also be gone -- proves
        # the FIRST successfully-appended event's insert was rolled back too, not just the
        # second (failed) one
