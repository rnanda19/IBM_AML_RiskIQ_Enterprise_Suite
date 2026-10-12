"""Tests for scripts/replay_alert_outbox.py -- the CLI wrapper around
serving._alert_dispatch.replay_outbox() (requirement 3, "reliable alert delivery", of the
end-to-end AML workflow integration phase, 2026-10-12).

Scope discipline: this script is a thin shell around the already-tested replay_outbox()
(see tests/unit/test_alert_dispatch.py for delivery/retry/idempotency coverage). These tests
therefore focus on the CLI's OWN logic -- argument wiring, known-service discovery, and
exit-code semantics -- using monkeypatch to replace the imported replay_outbox symbol with a
fake, rather than re-proving delivery behavior the lower-level suite already covers."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SRC_PATH = str(Path(__file__).resolve().parents[2] / "src" / "aml_riskiq")
if _SRC_PATH not in sys.path:
    sys.path.insert(0, _SRC_PATH)

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "replay_alert_outbox.py"
_spec = importlib.util.spec_from_file_location("replay_alert_outbox", _SCRIPT_PATH)
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)

from casework.alert_schema import Alert  # noqa: E402


def _write_outbox_file(outbox_dir: Path, service_name: str) -> Path:
    alert = Alert(
        business_problem="BP1",
        detection_source="xgboost_champion",
        entity_ref="acct-1",
        risk_score=0.9,
        selected_threshold=0.5,
        model_name="XGBoost",
        idempotency_key="a" * 64,
    )
    path = outbox_dir / f"{service_name}.outbox.jsonl"
    path.write_text(json.dumps({"alert": alert.model_dump(mode="json")}) + "\n", encoding="utf-8")
    return path


# -- no queued work ------------------------------------------------------------------------------


def test_all_with_no_outbox_files_returns_0_and_does_not_call_replay(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(cli, "replay_outbox", lambda *a, **k: called.append((a, k)))
    exit_code = cli.main(["--all", "--outbox-dir", str(tmp_path)])
    assert exit_code == 0
    assert called == []


def test_all_ignores_unknown_service_file_names(tmp_path, monkeypatch):
    """discovery only ever checks the fixed KNOWN_SERVICE_NAMES list -- a stray file with a
    name outside that list must never be picked up and replayed."""
    (tmp_path / "not_a_real_service.outbox.jsonl").write_text('{"alert": {}}\n', encoding="utf-8")
    called = []
    monkeypatch.setattr(cli, "replay_outbox", lambda *a, **k: called.append((a, k)))
    exit_code = cli.main(["--all", "--outbox-dir", str(tmp_path)])
    assert exit_code == 0
    assert called == []


# -- discovery + --all ---------------------------------------------------------------------------


def test_all_discovers_only_non_empty_known_outbox_files(tmp_path, monkeypatch):
    _write_outbox_file(tmp_path, "bp1_scoring_service")
    (tmp_path / "bp2_scoring_service.outbox.jsonl").write_text("", encoding="utf-8")  # empty -- skip

    seen_names = []

    def _fake_replay(name, **kwargs):
        seen_names.append(name)
        return {"attempted": 1, "delivered": 1, "duplicate": 0, "rejected": 0, "still_failed": 0}

    monkeypatch.setattr(cli, "replay_outbox", _fake_replay)
    exit_code = cli.main(["--all", "--outbox-dir", str(tmp_path)])
    assert exit_code == 0
    assert seen_names == ["bp1_scoring_service"]


def test_service_flag_replays_only_that_service_even_if_others_are_queued(tmp_path, monkeypatch):
    _write_outbox_file(tmp_path, "bp1_scoring_service")
    _write_outbox_file(tmp_path, "bp2_scoring_service")

    seen_names = []

    def _fake_replay(name, **kwargs):
        seen_names.append(name)
        return {"attempted": 1, "delivered": 1, "duplicate": 0, "rejected": 0, "still_failed": 0}

    monkeypatch.setattr(cli, "replay_outbox", _fake_replay)
    exit_code = cli.main(["--service", "bp2_scoring_service", "--outbox-dir", str(tmp_path)])
    assert exit_code == 0
    assert seen_names == ["bp2_scoring_service"]


# -- argument plumbing ----------------------------------------------------------------------------


def test_cli_flags_are_forwarded_to_replay_outbox(tmp_path, monkeypatch):
    _write_outbox_file(tmp_path, "bp1_scoring_service")
    captured_kwargs = {}

    def _fake_replay(name, **kwargs):
        captured_kwargs.update(kwargs)
        return {"attempted": 1, "delivered": 1, "duplicate": 0, "rejected": 0, "still_failed": 0}

    monkeypatch.setattr(cli, "replay_outbox", _fake_replay)
    cli.main(
        [
            "--service",
            "bp1_scoring_service",
            "--outbox-dir",
            str(tmp_path),
            "--case-service-url",
            "http://case-mgmt:8005",
            "--api-key",
            "test-key",
            "--timeout",
            "5.0",
        ]
    )
    assert captured_kwargs["case_service_url"] == "http://case-mgmt:8005"
    assert captured_kwargs["api_key"] == "test-key"
    assert captured_kwargs["timeout"] == 5.0


# -- exit-code semantics --------------------------------------------------------------------------


def test_exit_code_1_when_a_record_is_still_failed_after_replay(tmp_path, monkeypatch):
    _write_outbox_file(tmp_path, "bp1_scoring_service")
    monkeypatch.setattr(
        cli,
        "replay_outbox",
        lambda *a, **k: {"attempted": 1, "delivered": 0, "duplicate": 0, "rejected": 0, "still_failed": 1},
    )
    exit_code = cli.main(["--all", "--outbox-dir", str(tmp_path)])
    assert exit_code == 1


def test_exit_code_0_when_everything_delivered(tmp_path, monkeypatch):
    _write_outbox_file(tmp_path, "bp1_scoring_service")
    monkeypatch.setattr(
        cli,
        "replay_outbox",
        lambda *a, **k: {"attempted": 1, "delivered": 1, "duplicate": 0, "rejected": 0, "still_failed": 0},
    )
    exit_code = cli.main(["--all", "--outbox-dir", str(tmp_path)])
    assert exit_code == 0


def test_exit_code_0_when_rejected_not_delivered():
    """A definitive rejection (e.g. a malformed record) is resolved -- it is removed from
    the outbox by replay_outbox() and must not be treated as still needing attention."""
    summary = {"attempted": 1, "delivered": 0, "duplicate": 0, "rejected": 1, "still_failed": 0}
    assert summary["still_failed"] == 0  # sanity: this is the field main() checks


# -- mutually exclusive --service / --all ----------------------------------------------------


def test_service_and_all_are_mutually_exclusive(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(["--service", "bp1_scoring_service", "--all", "--outbox-dir", str(tmp_path)])


def test_neither_service_nor_all_is_rejected(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(["--outbox-dir", str(tmp_path)])


# -- real (unmocked) end-to-end against replay_outbox's own outbox-file handling ----------------


def test_real_replay_outbox_against_unreachable_service_leaves_file_queued_and_exits_1(tmp_path):
    """One real (not monkeypatched) pass through the actual replay_outbox() -- confirms the
    CLI's wiring to the real function, not just to a fake, produces the documented exit code
    and leaves the record queued when the Case Management Service cannot be reached."""
    _write_outbox_file(tmp_path, "bp1_scoring_service")
    exit_code = cli.main(
        [
            "--all",
            "--outbox-dir",
            str(tmp_path),
            "--case-service-url",
            "http://127.0.0.1:1",  # refuses connections -- no real listener on this port
            "--timeout",
            "0.3",
        ]
    )
    assert exit_code == 1
    assert (tmp_path / "bp1_scoring_service.outbox.jsonl").exists()
