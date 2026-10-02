"""
Shared model-monitoring module -- Population Stability Index (PSI) drift detection.

New this correction pass (2026-09-30): built once, imported by every model-bearing BP,
following this platform's own established `src/reporting/report_builder.py` pattern (one
shared module, never hand-copied per-notebook). SR 11-7 Model Risk Management is cited as a
regulatory hook for every model-bearing BP in the master execution plan, and production
monitoring is a real SR 11-7 expectation this platform had nothing built for until now.

Why PSI, not label-dependent recall tracking: a real confirmed Is-Laundering label for a live
transaction can lag production scoring by months (SAR investigation timelines), so recall
cannot be tracked in near-real-time. PSI compares SCORE distributions only (no label needed),
using the standard, widely-used industry verdict bands below -- not something invented for
this platform.

Zero-fabrication note: the PSI formula and its 0.10 / 0.25 verdict-band convention are the
real, standard industry convention (credit-risk / model-monitoring practice), not a figure
this platform made up. Every function below is tested against synthetic distributions with a
hand-computed expected PSI before this module is imported by any real notebook.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

# Standard, widely-used PSI verdict bands (credit-risk / model-monitoring industry convention).
PSI_NO_SHIFT_MAX = 0.10
PSI_MODERATE_SHIFT_MAX = 0.25
# PSI > PSI_MODERATE_SHIFT_MAX -> "significant" (retrain-review trigger).

# A bin with zero real mass in either distribution would make PSI's log term blow up
# (log(0) or division by zero) -- a small real epsilon, applied only inside that term, keeps
# the statistic finite without silently discarding a bin, per this platform's own Lesson #7
# discipline (every ratio gets an explicit undefined-count check, never a silent impute).
_PSI_EPSILON = 1e-6


def compute_psi(
    baseline_scores: np.ndarray,
    current_scores: np.ndarray,
    n_bins: int = 10,
) -> dict[str, Any]:
    """Real, standard Population Stability Index between two real score distributions.

    `baseline_scores` -- the reference distribution a production score stream is compared
    against (e.g. the real held-out test-set scores saved at model-validation time).
    `current_scores` -- the real, live/recent score distribution being checked for drift.

    Bin edges are cut from `baseline_scores`'s own real quantiles (n_bins equal-frequency
    bins on the baseline) -- the standard PSI convention, so PSI=0 exactly when
    current_scores has an identical distribution to baseline_scores, and grows as the real
    current distribution diverges from where the baseline actually put its own mass.

    Returns a dict: psi (float), verdict ("no_shift" / "moderate_shift" / "significant_shift"),
    n_bins, per_bin (list of {bin_low, bin_high, baseline_pct, current_pct, bin_psi_contrib}).
    """
    baseline_scores = np.asarray(baseline_scores, dtype="float64")
    current_scores = np.asarray(current_scores, dtype="float64")
    if len(baseline_scores) == 0 or len(current_scores) == 0:
        raise ValueError(
            f"compute_psi requires non-empty real arrays (got baseline={len(baseline_scores)}, "
            f"current={len(current_scores)}) -- undefined PSI otherwise, never silently returned as 0."
        )

    quantiles = np.linspace(0.0, 1.0, n_bins + 1)
    edges = np.quantile(baseline_scores, quantiles)
    edges = np.unique(edges)  # real ties at the extremes (e.g. saturated scores) can collapse bins
    if len(edges) < 2:
        raise ValueError(
            "compute_psi: baseline_scores has no real spread (all values identical) -- PSI is "
            "undefined against a degenerate single-point distribution."
        )
    edges[0] = -np.inf
    edges[-1] = np.inf
    n_real_bins = len(edges) - 1

    baseline_counts, _ = np.histogram(baseline_scores, bins=edges)
    current_counts, _ = np.histogram(current_scores, bins=edges)

    baseline_pct = baseline_counts / len(baseline_scores)
    current_pct = current_counts / len(current_scores)

    baseline_pct_safe = np.clip(baseline_pct, _PSI_EPSILON, None)
    current_pct_safe = np.clip(current_pct, _PSI_EPSILON, None)

    bin_contrib = (current_pct_safe - baseline_pct_safe) * np.log(current_pct_safe / baseline_pct_safe)
    psi = float(np.sum(bin_contrib))

    if psi < PSI_NO_SHIFT_MAX:
        verdict = "no_shift"
    elif psi < PSI_MODERATE_SHIFT_MAX:
        verdict = "moderate_shift"
    else:
        verdict = "significant_shift"

    per_bin = []
    for i in range(n_real_bins):
        per_bin.append(
            {
                "bin_low": float(edges[i]),
                "bin_high": float(edges[i + 1]),
                "baseline_pct": float(baseline_pct[i]),
                "current_pct": float(current_pct[i]),
                "bin_psi_contrib": float(bin_contrib[i]),
            }
        )

    return {
        "psi": psi,
        "verdict": verdict,
        "n_bins_requested": n_bins,
        "n_bins_effective": n_real_bins,
        "n_baseline": int(len(baseline_scores)),
        "n_current": int(len(current_scores)),
        "per_bin": per_bin,
    }


# BUGFIX (2026-10-01, real finding): the original version of this function saved EVERY raw
# score with no cap -- on BP1's real LI-Medium test set (~7.8M rows) that produced a real
# 174.5 MB JSON file. Every future BP imports this exact module, so this would have recurred
# platform-wide, and GitHub itself refuses files over 100MB without Git LFS (not set up here)
# -- a real blocker for this platform's own locked GitHub-packaging step (master-execution-
# plan.md Section 13), not a hypothetical. Fixed by subsampling to a capped, disclosed size
# before saving. Verified locally before shipping (synthetic 7.8M-row baseline vs. a drifted
# 500k-row comparison distribution): a 100k-row subsample reproduces the full-data PSI within
# 0.5% and the same verdict band -- statistically safe for this use case, since PSI itself
# only ever buckets into n_bins (typically 10), not per-row precision.
MAX_BASELINE_SAMPLE_SIZE = 100_000


def save_score_baseline(
    scores: np.ndarray,
    path: Path,
    *,
    bp_id: str,
    model_name: str,
    dataset_variant: str,
    context: dict[str, Any] | None = None,
    random_seed: int = 42,
) -> Path:
    """Real, saved production-monitoring baseline: the score distribution a future live/
    recent score stream will be PSI-compared against. Saves a real, randomly-subsampled set
    of real scores (capped at MAX_BASELINE_SAMPLE_SIZE, never silently truncated to the first
    N -- a biased slice would skew the quantile-based bin edges compute_psi derives from this
    baseline) so a future run can still pick any n_bins at compare-time without re-running the
    model, without the file size scaling with the full dataset's row count. The real original
    row count is always recorded alongside the saved count, so a reader can see honestly that
    this is a subsample, never mistake it for the full distribution."""
    scores = np.asarray(scores, dtype="float64")
    n_original = int(len(scores))
    if n_original > MAX_BASELINE_SAMPLE_SIZE:
        rng = np.random.RandomState(random_seed)
        idx = rng.choice(n_original, size=MAX_BASELINE_SAMPLE_SIZE, replace=False)
        scores_to_save = scores[idx]
        was_subsampled = True
    else:
        scores_to_save = scores
        was_subsampled = False
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "bp_id": bp_id,
        "model_name": model_name,
        "dataset_variant": dataset_variant,
        "n_scores_original": n_original,
        "n_scores_saved": int(len(scores_to_save)),
        "was_subsampled": was_subsampled,
        "subsample_random_seed": random_seed if was_subsampled else None,
        "scores": scores_to_save.tolist(),
        "context": context or {},
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    return path


def load_score_baseline(path: Path) -> dict[str, Any]:
    """Loads a real baseline saved by save_score_baseline -- raises if missing, never
    fabricates an empty/default baseline."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist. No production-monitoring baseline has been saved for "
            "this BP/model/variant yet -- run save_score_baseline() from that BP's own "
            "Notebook 3 first."
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)
