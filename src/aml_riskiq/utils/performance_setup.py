"""
IBM AML RiskIQ Enterprise Suite - WARP resource-governance module.

Standing rule (per the user's stated preference, carried forward from the
AMEX/Home Credit platforms): target up to ~92% of available CPU threads and
RAM, NEVER 100% - 100% utilization hung the reference laptop during a prior
platform's Phase 3 (real incident). This is a safety CAP, not a floor to
force by padding workload.

MUST be called BEFORE importing numpy/pandas/polars/scikit-learn/xgboost/
lightgbm/catboost - those libraries read thread-related environment
variables at import time, not after (Lessons Learned Applied #5).

Thermal protection: thermal_checkpoint() below is a real time.sleep(), cadence
CONFIRMED at 12 seconds by the user 2026-09-29 (no longer an assumption) -
call it after any heavy operation (large fit, large groupby/aggregation,
large Monte Carlo loop) on this 8-core/16-thread laptop.

No GPU/NPU path exists in this codebase's model stack - every model here
(XGBoost/LightGBM/CatBoost/scikit-learn) runs CPU-only, so this module only
governs CPU threads and RAM, never a clock speed (clock speed is a
BIOS/OS-firmware setting, outside any Python module's control).
"""

from __future__ import annotations

import functools
import os
import time
from contextlib import contextmanager
from typing import Optional

CPU_CEILING_FRACTION = 0.92
RAM_CEILING_FRACTION = 0.92
THERMAL_CHECKPOINT_SECONDS = 12  # user-confirmed 2026-09-29

_THREAD_ENV_VARS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "POLARS_MAX_THREADS",
    "RAYON_NUM_THREADS",
)


def configure_performance(cpu_fraction: float = CPU_CEILING_FRACTION) -> dict:
    """Set a hardware-detected thread ceiling via environment variables.

    Call this FIRST, before any heavy numerical-library import. Returns the
    detected configuration (purely descriptive - not a verdict on any run).
    """
    try:
        import multiprocessing

        logical_cores = multiprocessing.cpu_count()
    except Exception:
        logical_cores = 1

    n_threads = max(1, int(logical_cores * cpu_fraction))

    for var in _THREAD_ENV_VARS:
        os.environ[var] = str(n_threads)

    return {
        "logical_cores_detected": logical_cores,
        "cpu_ceiling_fraction": cpu_fraction,
        "threads_configured": n_threads,
        "note": "Safety CAP, not a floor - never pad workload to force higher utilization.",
    }


def thermal_checkpoint(seconds: int = THERMAL_CHECKPOINT_SECONDS, label: str = "") -> float:
    """Real pause after a heavy operation - a genuine time.sleep(), not a no-op.

    Cadence confirmed by the user at 12 seconds (2026-09-29). Call this after
    any large .fit()/.transform(), large groupby/aggregation, or Monte Carlo
    loop, to let the laptop's thermals settle between heavy steps on this
    8-core/16-thread machine. Returns the actual seconds slept (never a
    fabricated/assumed number - measured with perf_counter).
    """
    start = time.perf_counter()
    time.sleep(seconds)
    elapsed = time.perf_counter() - start
    tag = f" [{label}]" if label else ""
    print(f"[THERMAL_CHECKPOINT]{tag} slept {elapsed:.2f}s (target {seconds}s)")
    return elapsed


def pin_cpu_affinity(n_threads: Optional[int] = None) -> bool:
    """Best-effort CPU-affinity pin via psutil.

    Returns False (no-op) on platforms without process-affinity support,
    or if psutil is unavailable - never raises.
    """
    try:
        import psutil

        proc = psutil.Process(os.getpid())
        if not hasattr(proc, "cpu_affinity"):
            return False
        all_cpus = list(range(psutil.cpu_count(logical=True) or 1))
        n = n_threads or max(1, int(len(all_cpus) * CPU_CEILING_FRACTION))
        proc.cpu_affinity(all_cpus[:n])
        return True
    except Exception:
        return False


def check_ram_headroom(ram_fraction: float = RAM_CEILING_FRACTION) -> dict:
    """Report real RAM headroom via psutil. Returns an explicit error key
    (never a fabricated number) if psutil is unavailable.

    REAL ISSUE FLAGGED (user's own real LI-Medium run, 2026-10-01): the user observed Task
    Manager showing ~15GB free at roughly the time the RAM gate reported only ~3.74GB
    available and tripped. `vm.available` (the figure this function has always reported) is
    the same underlying Windows API Task Manager's own "Available" column reads from, so a
    gap this large is almost certainly a TIMING difference -- this function captures memory
    at the exact instant immediately before a heavy step, while a Task Manager glance even a
    few seconds later (after Python's exception unwinding and any temp buffers release) can
    look very different -- rather than the two numbers disagreeing about the same instant.
    To make this verifiable instead of argued about, every field psutil exposes is now
    returned and printed (not just available_gb), so a real run's own output can be compared
    directly against a Task Manager screenshot taken at that same moment."""
    try:
        import psutil

        vm = psutil.virtual_memory()
        total_gb = vm.total / (1024**3)
        available_gb = vm.available / (1024**3)
        used_gb = vm.used / (1024**3)
        free_gb = vm.free / (1024**3)
        ceiling_gb = total_gb * ram_fraction
        result = {
            "total_ram_gb": round(total_gb, 2),
            "available_ram_gb": round(available_gb, 2),
            "used_ram_gb": round(used_gb, 2),
            "free_ram_gb": round(free_gb, 2),
            "percent_used": vm.percent,
            "ram_ceiling_gb": round(ceiling_gb, 2),
            "ram_ceiling_fraction": ram_fraction,
        }
        for extra_field in ("cached", "buffers"):
            if hasattr(vm, extra_field):
                result[f"{extra_field}_gb"] = round(getattr(vm, extra_field) / (1024**3), 2)
        return result
    except Exception:
        return {"error": "psutil not available - RAM headroom not checked"}


def assert_ram_safe(min_available_gb: float = 3.0, label: str = "") -> dict:
    """Real, ENFORCING RAM safety gate -- unlike check_ram_headroom() (report-only, never
    stopped anything), this RAISES MemoryError and stops execution BEFORE a risky step if
    real available RAM is already below min_available_gb.

    Added 2026-09-30 after a real incident: BP2 Notebook 3 hung the reference laptop at
    100% RAM usage and required a hard restart. Root cause (confirmed): a row-wise Python
    loop (DataFrame.agg("|".join, axis=1)) building a join key over Trans.csv's real ~31M
    rows -- not vectorized despite looking like a one-liner, and this module's own
    check_ram_headroom() only ever printed a number, never stopped anything. Call this
    function immediately before any step already disclosed as memory-heavy (a large
    row-wise key build, a large merge, a RandomForest fit on a multi-million-row frame).

    2026-10-01 addendum: now prints the FULL real psutil breakdown (used/free/cached, not
    just available) on both PASS and FAIL, so a disputed reading can be checked directly
    against Task Manager at the same instant instead of relying on a single number."""
    headroom = check_ram_headroom()
    if "error" in headroom:
        print(
            f"  [RAM-GATE]{f' [{label}]' if label else ''} SKIPPED -- {headroom['error']} "
            f"(cannot enforce the safety gate without psutil; proceeding without a real check)."
        )
        return headroom
    detail = (
        f"available={headroom['available_ram_gb']:.2f}GB, used={headroom.get('used_ram_gb', float('nan')):.2f}GB, "  # noqa: E501
        f"free={headroom.get('free_ram_gb', float('nan')):.2f}GB, percent_used={headroom.get('percent_used', 'n/a')}%"  # noqa: E501
    )
    if headroom["available_ram_gb"] < min_available_gb:
        raise MemoryError(
            f"RAM safety gate tripped{f' at [{label}]' if label else ''}: only "
            f"{headroom['available_ram_gb']:.2f} GB available (need >= {min_available_gb:.2f} GB "
            f"headroom before this step). Full real reading at this instant: {detail}. "
            f"Stopping now, before this step risks hanging the "
            f"machine at 100% RAM (real incident, 2026-09-30) -- close other applications/"
            f"notebooks/browser tabs to free memory, or restart the kernel to release memory "
            f"held by earlier cells, then re-run."
        )
    print(f"  [RAM-GATE]{f' [{label}]' if label else ''} PASS -- {detail}")
    return headroom


def load_csv_cached(csv_path, parquet_cache_path=None, **read_csv_kwargs):
    """Read a CSV once, cache it as Parquet for reuse (WARP: Parquet over
    CSV for repeatedly-read tables - Section 9.3 technique #3). Returns a
    pandas DataFrame.

    On the first call for a given csv_path, this is exactly as slow as a
    plain CSV read (plus a one-time Parquet write). Every subsequent call
    against the same cache path reads the much cheaper Parquet file
    instead. Never silently returns stale data: the cache is only used when
    it is newer than the source CSV's modification time.
    """
    from pathlib import Path

    import pandas as pd

    csv_path = Path(csv_path)
    cache_path = Path(parquet_cache_path) if parquet_cache_path else csv_path.with_suffix(".parquet")

    if cache_path.exists() and cache_path.stat().st_mtime >= csv_path.stat().st_mtime:
        return pd.read_parquet(cache_path)

    df = pd.read_csv(csv_path, **read_csv_kwargs)
    try:
        df.to_parquet(cache_path, index=False)
    except Exception:
        pass  # caching is a performance optimization, never a hard requirement
    return df


@contextmanager
def timer(label: str):
    """Section 9.3 technique #8: timer/timed instrumentation on every heavy step."""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        print(f"[TIMER] {label}: {elapsed:.4f}s")


def timed(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with timer(func.__name__):
            return func(*args, **kwargs)

    return wrapper
