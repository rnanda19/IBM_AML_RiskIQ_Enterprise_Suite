"""Regression guard: every AML_RISKIQ_* environment variable referenced by src/ must be
documented in .env.example.

This exists because of a real gap found during the 2026-10-12 production-readiness review:
.env.example documented only 4 of the 13 environment variables the codebase actually reads
(the Case Management Service's DB path, the scoring-to-alert dispatch settings, and the
project-root override were all missing). A silent config-example drift like that is exactly
the kind of thing Improvement 3's acceptance criteria ("configuration examples") calls out --
so this test makes the two sides of that contract machine-checked instead of trusted by hand.

This is a documentation-completeness check, not a secrets check: it only confirms every real
env-var NAME appears somewhere in the example file (commented out or not). It does not, and
must not, assert anything about real secret VALUES -- see SECRETS_MANAGEMENT.md.
"""

from __future__ import annotations

import re
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_DIR = _PROJECT_ROOT / "src"
_ENV_EXAMPLE = _PROJECT_ROOT / ".env.example"

_ENV_VAR_PATTERN = re.compile(r"AML_RISKIQ_[A-Z_]+")

# A handful of per-BP, non-"AML_RISKIQ_"-prefixed variables (e.g. BP1_DATASET_VARIANT) are
# intentionally out of scope for this check -- it is scoped to the shared AML_RISKIQ_* family,
# which is where the real gap was found.


def _env_vars_referenced_in_source() -> set[str]:
    found: set[str] = set()
    for py_file in _SRC_DIR.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        found.update(_ENV_VAR_PATTERN.findall(text))
    return found


def _env_vars_documented_in_example() -> set[str]:
    text = _ENV_EXAMPLE.read_text(encoding="utf-8")
    return set(_ENV_VAR_PATTERN.findall(text))


def test_env_example_exists() -> None:
    assert _ENV_EXAMPLE.is_file(), ".env.example must exist at the project root"


def test_source_actually_references_some_env_vars() -> None:
    # Sanity check on the scan itself: if this ever comes back empty, the glob/regex broke
    # silently rather than the codebase genuinely dropping all AML_RISKIQ_* env var usage.
    referenced = _env_vars_referenced_in_source()
    assert len(referenced) >= 10, (
        f"expected at least 10 distinct AML_RISKIQ_* env vars referenced under src/, "
        f"found {len(referenced)}: {sorted(referenced)} -- did the scan break?"
    )


def test_every_env_var_referenced_in_source_is_documented_in_env_example() -> None:
    referenced = _env_vars_referenced_in_source()
    documented = _env_vars_documented_in_example()
    missing = sorted(referenced - documented)
    assert not missing, (
        "the following AML_RISKIQ_* environment variables are read somewhere under src/ "
        f"but are not mentioned in .env.example: {missing}. Add a documented, commented-out "
        "example line for each (see the existing entries in .env.example for the format)."
    )
