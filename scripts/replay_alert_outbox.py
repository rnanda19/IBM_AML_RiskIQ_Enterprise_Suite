#!/usr/bin/env python3
"""
scripts/replay_alert_outbox.py -- CLI wrapper around serving._alert_dispatch.replay_outbox(),
the operator-invoked half of the outbox pattern (requirement 3, "reliable alert delivery", of
the 2026-10-12 End-to-End AML Workflow Integration phase). A queued alert that
dispatch_alert() could not deliver inline (a sustained Case Management Service outage) sits in
data/alert_outbox/<service_name>.outbox.jsonl until this script -- or an equivalent
re-invocation of replay_outbox() -- is run. This is the "recoverable" half of "failures are
visible and recoverable": nothing here is automatic or scheduled; it is the thing an operator
(or a deployment's own retry job) runs once the Case Management Service is confirmed reachable
again.

Safe to run more than once, including after a crash mid-replay: replay_outbox() relies on the
Case Management Service's own idempotency check on POST /alerts/ingest (keyed on each alert's
deterministic idempotency_key, enforced by a real database UNIQUE index -- see
casework/store.py), so a record already delivered on a previous replay attempt is recognized as
a duplicate, never redelivered as a second alert.

Scope discipline: this script is a thin CLI shell around the already-tested replay_outbox() --
it contains no new delivery, retry, or idempotency logic of its own (that would be a second,
divergent copy of logic _alert_dispatch.py already owns and tests cover).

Usage:
    python scripts/replay_alert_outbox.py --service bp1_scoring_service
    python scripts/replay_alert_outbox.py --all
    python scripts/replay_alert_outbox.py --all \
        --case-service-url http://localhost:8005 --api-key <key>

Every flag is optional except exactly one of --service / --all; anything not passed on the
command line falls back to the same environment variables dispatch_alert() itself reads
(AML_RISKIQ_CASE_SERVICE_URL, AML_RISKIQ_CASE_SERVICE_API_KEY, AML_RISKIQ_ALERT_OUTBOX_DIR) --
prefer the env var over --api-key so a real key never lands in shell history.

Exit code: 0 if every attempted record ended up delivered, recognized as a duplicate, or
definitively rejected (nothing left queued afterwards); 1 if any record is still queued after
the attempt -- so this composes cleanly as a CI/cron step that should fail loudly on a
persistent outage rather than exiting 0 while alerts remain stuck.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC_PATH = str(Path(__file__).resolve().parents[1] / "src" / "aml_riskiq")
if _SRC_PATH not in sys.path:
    sys.path.insert(0, _SRC_PATH)

from serving._alert_dispatch import outbox_path_for, replay_outbox  # noqa: E402

# Keep in sync with the service_name values the 5 scoring services themselves pass to
# maybe_generate_and_dispatch_alert() (see each src/aml_riskiq/serving/bp*_scoring_service.py) --
# an outbox file is only ever written under exactly one of these names by outbox_path_for().
KNOWN_SERVICE_NAMES = (
    "bp1_scoring_service",
    "bp2_scoring_service",
    "bp3_rule_scoring_service",
    "bp4_scoring_service",
    "bp5_scoring_service",
)


def _discover_queued_service_names(outbox_dir: Path | None) -> list[str]:
    """Returns the subset of KNOWN_SERVICE_NAMES that currently has a non-empty outbox file
    on disk. Never infers a service name from an arbitrary file found in the directory --
    only ever checks the fixed, known names, the same discipline outbox_path_for() itself
    uses to keep each service's queue in its own clearly-named file."""
    found = []
    for name in KNOWN_SERVICE_NAMES:
        path = outbox_path_for(name, outbox_dir=outbox_dir)
        if path.exists() and path.stat().st_size > 0:
            found.append(name)
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--service",
        choices=KNOWN_SERVICE_NAMES,
        help="Replay only this one service's outbox file.",
    )
    target.add_argument(
        "--all",
        action="store_true",
        help="Replay every known service's outbox file that currently has queued records.",
    )
    parser.add_argument(
        "--outbox-dir",
        type=Path,
        default=None,
        help="Override the outbox directory (defaults to AML_RISKIQ_ALERT_OUTBOX_DIR, else "
        "<repo>/data/alert_outbox).",
    )
    parser.add_argument(
        "--case-service-url",
        default=None,
        help="Override the Case Management Service URL (defaults to AML_RISKIQ_CASE_SERVICE_URL).",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Override the case-service API key (defaults to AML_RISKIQ_CASE_SERVICE_API_KEY). "
        "Prefer the env var over this flag so the key never appears in shell history.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Per-request timeout in seconds (defaults to dispatch_alert()'s own defalt).",
    )
    args = parser.parse_args(argv)

    service_names = [args.service] if args.service else _discover_queued_service_names(args.outbox_dir)

    if not service_names:
        resolved_dir = outbox_path_for(KNOWN_SERVICE_NAMES[0], outbox_dir=args.outbox_dir).parent
        print(f"No queued outbox files found under {resolved_dir}. Nothing to replay.")
        return 0

    exit_code = 0
    for name in service_names:
        summary = replay_outbox(
            name,
            outbox_dir=args.outbox_dir,
            case_service_url=args.case_service_url,
            api_key=args.api_key,
            timeout=args.timeout,
        )
        print(
            f"[{name}] attempted={summary['attempted']} delivered={summary['delivered']} "
            f"duplicate={summary['duplicate']} rejected={summary['rejected']} "
            f"still_failed={summary['still_failed']}"
        )
        if summary["still_failed"] > 0:
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
