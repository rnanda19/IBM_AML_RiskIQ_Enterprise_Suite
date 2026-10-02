#!/usr/bin/env python3
"""
CI check: every real .ipynb under notebooks/ loads as valid Jupyter JSON (nbformat) and every
code cell's Python source compiles cleanly (ast.parse) -- a real, catchable syntax error in a
code cell is caught here, in seconds, on every push/PR, instead of only being discovered the
next time the user manually opens and runs that notebook in Jupyter.

Found during the 2026-10-02 enterprise-hardening review: ci.yml's `notebook-syntax-check` job
already existed and was already wired into CI, but the script it called
(scripts/check_notebook_syntax.py) never existed on disk -- the job always failed to find it
and was only not failing CI because the workflow step ends with `|| true`, so it silently
"passed" on every run while checking nothing at all. This is that missing script.

Scope discipline: this performs a SYNTAX check only (ast.parse on each code cell's real
source) -- it never imports, executes, or runs any cell, and never touches real data or
trained models, consistent with this project's standing execution-boundary rule. Lines that
are Jupyter-only magics/shell escapes (starting with %, %%, or !) are stripped before parsing,
since they are valid in a live kernel but not valid standalone Python syntax -- the same
translation `nbconvert --to script` performs internally.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import nbformat

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS_DIR = PROJECT_ROOT / "notebooks"


def _stub_magics(source: str) -> str:
    """Replace Jupyter magic/shell-escape lines with a harmless no-op statement so the real
    Python statements around them can still be syntax-checked. Never changes real code
    lines."""
    out_lines = []
    for line in source.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("%") or stripped.startswith("!"):
            out_lines.append("pass  # (stubbed Jupyter magic/shell line for syntax check)")
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


def check_notebook(nb_path: Path) -> list[str]:
    """Returns a list of real error strings for this notebook (empty list = clean)."""
    errors: list[str] = []
    try:
        nb = nbformat.read(nb_path, as_version=4)
    except Exception as exc:  # noqa: BLE001 -- any parse failure is a real, reportable error
        return [f"{nb_path}: could not parse as a notebook ({exc})"]

    for i, cell in enumerate(nb.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        source = cell.get("source", "")
        if isinstance(source, list):
            source = "".join(source)
        if not source.strip():
            continue
        try:
            ast.parse(_stub_magics(source), filename=str(nb_path))
        except SyntaxError as exc:
            errors.append(f"{nb_path} [code cell {i}]: {exc.__class__.__name__}: {exc}")
    return errors


def main() -> int:
    if not NOTEBOOKS_DIR.exists():
        print(f"SKIPPED -- {NOTEBOOKS_DIR} does not exist.")
        return 0

    nb_paths = sorted(NOTEBOOKS_DIR.glob("**/*.ipynb"))
    nb_paths = [p for p in nb_paths if ".ipynb_checkpoints" not in p.parts]
    if not nb_paths:
        print(f"SKIPPED -- no .ipynb files found under {NOTEBOOKS_DIR}.")
        return 0

    all_errors: list[str] = []
    for nb_path in nb_paths:
        errs = check_notebook(nb_path)
        all_errors.extend(errs)
        status = "OK" if not errs else f"{len(errs)} ERROR(S)"
        print(f"[{status}] {nb_path.relative_to(PROJECT_ROOT)}")

    if all_errors:
        print(f"\n{len(all_errors)} real syntax error(s) found:")
        for e in all_errors:
            print(f"  - {e}")
        return 1

    print(f"\nAll {len(nb_paths)} notebook(s) passed syntax check (0 errors).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
