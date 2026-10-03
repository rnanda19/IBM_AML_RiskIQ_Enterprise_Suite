"""
IBM AML RiskIQ Enterprise Suite - robust project-root resolution.

Mirrors the proven pattern from the AMEX RiskIQ / Home Credit RiskIQ
platforms: env override -> walk upward from cwd looking for a marker ->
bounded well-known locations under the user's home directory.

Real, confirmed location (2026-09-29): C:\\Users\\rnand\\Documents\\IBM_AML_RiskIQ_Enterprise_Suite
(no longer an assumption - this is the real on-device path this suite lives at).
"""

from __future__ import annotations

import os
from pathlib import Path

MARKER_FILE = "PROJECT_STRUCTURE_LOCKED.md"
ENV_VAR = "AML_RISKIQ_SUITE_ROOT"

WELL_KNOWN_RELATIVE = [
    "Documents/IBM_AML_RiskIQ_Enterprise_Suite",
    "Downloads/IBM_AML_RiskIQ_Enterprise_Suite",
]


def find_suite_root(start: "Path | None" = None, max_up: int = 6) -> Path:
    """Resolve the IBM AML RiskIQ suite root directory.

    Resolution order (first match wins):
      1. AML_RISKIQ_SUITE_ROOT environment variable, if set and a real dir.
      2. Walking upward from `start` (default: cwd) looking for the real
         locked-structure marker file (PROJECT_STRUCTURE_LOCKED.md).
      3. A bounded list of well-known locations under the user's home dir.

    Raises FileNotFoundError with an actionable message if none resolve -
    never silently falls back to a fabricated/guessed path.
    """
    env_val = os.environ.get(ENV_VAR)
    if env_val:
        candidate = Path(env_val).expanduser()
        if candidate.is_dir():
            return candidate.resolve()

    cur = (start or Path.cwd()).resolve()
    for _ in range(max_up + 1):
        if (cur / MARKER_FILE).exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent

    home = Path.home()
    for rel in WELL_KNOWN_RELATIVE:
        candidate = home / rel
        if candidate.is_dir():
            return candidate.resolve()

    raise FileNotFoundError(
        "Could not resolve the IBM AML RiskIQ suite root. Fix one of:\n"
        f"  (a) set the {ENV_VAR} environment variable to your real project folder, or\n"
        "  (b) run this notebook from inside the project tree (any subfolder), or\n"
        "  (c) confirm PROJECT_STRUCTURE_LOCKED.md still exists at the real project root."
    )


def raw_data_dir(start: "Path | None" = None) -> Path:
    """Convenience: the project's data/raw/ directory, resolved off the real root."""
    return find_suite_root(start) / "data" / "raw"
