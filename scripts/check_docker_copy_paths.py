#!/usr/bin/env python3
"""
CI/make check: every `COPY <src> <dst>` line in every real src/docker/*/Dockerfile actually
resolves to a file or directory that exists on disk, relative to that Dockerfile's declared
build context (the repo root, per every one of these Dockerfiles' own header comment).

Found during the 2026-10-02 enterprise-hardening review: `make docker-verify` claimed (in its
own comment) to confirm "each BP's Dockerfile COPY paths resolve against its declared build
context", but its actual implementation only checked that Dockerfile/docker-compose.yml/
.dockerignore were PRESENT -- it never looked at a single COPY line. That gap is exactly how
a real bug slipped through undetected: bp1/bp2/bp3/bp4/bp5's Dockerfiles each copied their
model artifact(s) but never the real saved validation-report JSON their own service module
requires at import time (REPORT_PATH.exists() check, raises FileNotFoundError if missing) --
every one of those 5 images would have built "successfully" and then crashed on first
container start. This script is the real check the Makefile's comment already claimed to
have; `make docker-verify` now calls it instead of (or in addition to) the file-presence loop.

Scope discipline: this is a STATIC check -- it parses COPY source paths and calls Path.exists()
on them. It never invokes `docker build` (confirmed unavailable in this sandbox: `docker` is
not on PATH here), never executes a notebook, and never touches real data or trained models.
It closes the specific gap a real `docker build` would also have caught, without needing one.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCKER_DIR = PROJECT_ROOT / "src" / "docker"

# Matches a Dockerfile COPY instruction, including the backslash-continued multi-line form
# every Dockerfile in this project uses for a long source/destination pair, e.g.:
#   COPY models/bp1_.../bp1_notebook3_champion_li_medium.pkl \
#        ./models/bp1_.../bp1_notebook3_champion_li_medium.pkl
# Captures only the SOURCE path (the first whitespace-separated token) -- the destination
# path lives inside the image, not on this disk, so it is never checked against the real
# filesystem.
_COPY_RE = re.compile(r"^\s*COPY\s+(\S+)", re.MULTILINE)

# Destinations that are never real source paths (a multi-stage --from=... reference) -- none
# of this project's Dockerfiles currently use multi-stage builds, but this guard keeps the
# check honest if one is added later rather than mis-flagging it as a missing file.
_SKIP_PREFIXES = ("--from=",)

# Known, already-disclosed pending artifacts: real files that do not exist on this repo yet
# because they can only be produced by the USER re-running their own real notebook (this
# project's standing zero-pipeline-execution rule -- Claude writes and verifies code, it
# never runs the real notebooks to generate real business/model artifacts). Each entry here
# is cross-referenced in its own Dockerfile's header comment, which explains exactly which
# notebook re-run produces it. Flagged as a WARNING below, never silently skipped and never
# a hard CI failure for a gap this script cannot close itself.
KNOWN_PENDING_ARTIFACTS = {
    # bp3_rule_scoring_service.py's real, per-account near-train-flagged adjacency lookup --
    # see src/docker/bp3_network_graph_intelligence/Dockerfile's own header comment.
    "models/bp3_network_graph_intelligence/bp3_notebook3_near_train_flagged_lookup_li_medium.parquet",
}


def check_dockerfile(dockerfile: Path) -> tuple[list[str], list[str]]:
    """Returns (errors, pending_warnings) for one Dockerfile. errors empty + pending_warnings
    empty means every COPY source path resolved against the repo root (this Dockerfile's own
    declared build context, per its header comment and its docker-compose.yml's
    `build.context`). A non-empty pending_warnings list is not a failure -- see
    KNOWN_PENDING_ARTIFACTS above."""
    errors: list[str] = []
    pending: list[str] = []
    text = dockerfile.read_text(encoding="utf-8")
    for match in _COPY_RE.finditer(text):
        src = match.group(1)
        if src.startswith(_SKIP_PREFIXES):
            continue
        resolved = (PROJECT_ROOT / src).resolve()
        if resolved.exists():
            continue
        if src in KNOWN_PENDING_ARTIFACTS:
            pending.append(src)
            continue
        errors.append(
            f"{dockerfile.relative_to(PROJECT_ROOT)}: COPY source {src!r} does not exist at "
            f"{resolved} (resolved against the repo root, this Dockerfile's declared build "
            "context)."
        )
    return errors, pending


def main() -> int:
    dockerfiles = sorted(DOCKER_DIR.glob("*/Dockerfile"))
    if not dockerfiles:
        print(f"[check_docker_copy_paths] No Dockerfiles found under {DOCKER_DIR}.")
        return 0

    all_errors: list[str] = []
    for dockerfile in dockerfiles:
        errors, pending = check_dockerfile(dockerfile)
        rel = dockerfile.relative_to(PROJECT_ROOT)
        if errors:
            all_errors.extend(errors)
        elif pending:
            for src in pending:
                print(
                    f"[PENDING, disclosed] {rel}: {src!r} not yet generated on this machine -- "
                    "see this Dockerfile's own header comment for the notebook re-run that "
                    "produces it."
                )
        else:
            print(f"[OK] {rel}")

    if all_errors:
        print("\n[check_docker_copy_paths] FAILED -- missing COPY source(s):")
        for err in all_errors:
            print(f"  - {err}")
        return 1

    print(f"\nAll {len(dockerfiles)} Dockerfile(s) passed COPY-path check (0 unexplained missing sources).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
