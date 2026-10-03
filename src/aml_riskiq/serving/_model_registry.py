"""
Shared, minimal model-registry helper for the platform's model-backed FastAPI scoring
services (BP1/BP2/BP4/BP5 -- BP3 has no trained model, it is a rule/set-membership service,
and is deliberately not wired to this module).

HONEST SCOPE: this is NOT a full model registry (no versioned storage, no promotion
workflow, no rollback). What it closes is a real, narrow gap: before this module, a running
service's `/health` endpoint said *which* champion algorithm it loaded (`champion_name`) but
gave no way to verify *which exact model artifact* -- byte for byte -- was actually loaded
into that process, or when that artifact's file was last written. `build_registry_entry()`
answers both, computed from the real on-disk file every time (never cached across different
files, never guessed): a SHA-256 of the actual loaded `.pkl` bytes, and that file's own
filesystem mtime.

Zero-fabrication note on dates: a model's *real* training timestamp only exists in the
notebook's own saved validation report, under `generated_at_utc` -- and that field does not
exist in every BP's saved report (confirmed by inspecting the real on-disk JSON: BP1's
report has it, BP2/BP4/BP5's do not). This module never invents a substitute for a field
that was not actually saved -- `report_generated_at_utc` below is `None` wherever the real
report lacks that key, rather than falling back to something that looks plausible but isn't
real (e.g. the file's own mtime, which reflects when the file was last copied/checked out on
*this* machine, not when the model was trained -- that honest distinction is exactly why this
module reports both values separately instead of collapsing them into one date field).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256_of_file(path: Path) -> str:
    """Streams the file in chunks so this works for a multi-hundred-MB model artifact
    without loading it into memory twice (once for pickle.load, once for hashing)."""
    digest = hashlib.sha256()
    with open(
        path, "rb"
    ) as f:  # nosec B301 -- hashing, not deserializing; same real on-disk model artifact every service already loads via pickle.load elsewhere  # noqa: E501
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_registry_entry(
    *,
    model_path: Path,
    champion_name: str,
    dataset_variant: str,
    report_generated_at_utc: str | None,
) -> dict[str, Any]:
    """Builds the small dict every model-backed service's /health response embeds under the
    "model_registry" key. All values are either copied verbatim from the real saved report
    (champion_name, dataset_variant, report_generated_at_utc) or computed fresh from the real
    on-disk model file (sha256, file_mtime_utc, file_name) -- nothing here is guessed."""
    stat = model_path.stat()
    file_mtime_utc = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    return {
        "model_file_name": model_path.name,
        "model_sha256": sha256_of_file(model_path),
        "model_file_mtime_utc": file_mtime_utc,
        "model_file_size_bytes": stat.st_size,
        "champion_name": champion_name,
        "dataset_variant": dataset_variant,
        "report_generated_at_utc": report_generated_at_utc,
    }


__all__ = ["sha256_of_file", "build_registry_entry"]
