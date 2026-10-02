# ============================================================================
# NOTEBOOK 0 -- Environment Setup & Hardware Benchmark (SINGLE CELL -- paste this whole file into one Jupyter cell)
# ============================================================================

# # Notebook 0 — Environment Setup & Hardware Benchmark
# ## IBM AML RiskIQ Enterprise Suite — Platform-Wide (run once, before any Business Problem notebook)
# 
# **Purpose:** verify every library this platform needs is installed and importable, detect this machine's real
# hardware (CPU physical/logical cores, RAM, OS), and benchmark real per-thread-count throughput — all numbers
# below are measured live when this notebook runs, never assumed or hardcoded ahead of time (zero-fabrication
# standing rule).
# 
# **Project root:** `C:\Users\rnand\Documents\IBM_AML_RiskIQ_Enterprise_Suite\` (confirmed 2026-09-29).
# 
# **WARP resource governance:** `configure_performance()` is called in the very next cell, *before* any
# heavy numerical-library import (numpy/pandas/polars/scikit-learn/xgboost/lightgbm/catboost all read
# thread-related environment variables at import time — Lessons Learned Applied #5). Hard ceiling: ~92% of
# available CPU threads and RAM, never 100% (100% hung the reference laptop during a prior platform's Phase 3 —
# a real incident, not a hypothetical).
# 
# **Thermal protection:** `thermal_checkpoint()` — a real `time.sleep(12)`, cadence user-confirmed 2026-09-29 —
# runs once at the end of this notebook's benchmark loop, the only genuinely heavy step here.

import sys
from pathlib import Path

def _locate_project_root():
    # 1. Walk upward from cwd looking for the locked-structure marker.
    cur = Path.cwd()
    for _ in range(8):
        if (cur / "PROJECT_STRUCTURE_LOCKED.md").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    # 2. Fallback: the real, confirmed on-device location (2026-09-29).
    known = Path.home() / "Documents" / "IBM_AML_RiskIQ_Enterprise_Suite"
    if (known / "PROJECT_STRUCTURE_LOCKED.md").exists():
        return known
    raise FileNotFoundError(
        "Could not locate the project root. Checked: an upward walk from this notebook's "
        f"working directory ({Path.cwd()}), and {known}. Either save this notebook inside "
        "the project folder, or edit the 'known' path above to your real project location."
    )

_here = _locate_project_root()
sys.path.insert(0, str(_here / "src"))
print(f"Bootstrapped from: {_here}")

from utils.project_root import find_suite_root, raw_data_dir
from utils.performance_setup import configure_performance, thermal_checkpoint, check_ram_headroom, timer

PROJECT_ROOT = find_suite_root()
print(f"Resolved project root: {PROJECT_ROOT}")
assert PROJECT_ROOT.exists(), "Project root resolution failed — see project_root.py's FileNotFoundError message."

# WARP STEP 1 (must run before any heavy import below): set the real thread ceiling.
perf_config = configure_performance()
print("configure_performance() result (real, measured on this machine — not assumed):")
for k, v in perf_config.items():
    print(f"  {k}: {v}")

# ## 1. Real Hardware Detection
# Every value below is read live from this machine via `platform`/`psutil`/`os` — nothing here is copied from
# `configs/resource_limits.yaml`'s `[ASSUMPTION]`-flagged placeholders. Those placeholders get corrected against
# this cell's real output.

import os
import platform

import psutil

logical_cores = psutil.cpu_count(logical=True)
physical_cores = psutil.cpu_count(logical=False)
ram = check_ram_headroom()
cpu_freq = psutil.cpu_freq()

hardware_detected = {
    "os": f"{platform.system()} {platform.release()} ({platform.version()})",
    "python_version": sys.version.split()[0],
    "physical_cores": physical_cores,
    "logical_threads": logical_cores,
    "cpu_max_freq_mhz_reported": getattr(cpu_freq, "max", None),
    "cpu_current_freq_mhz": getattr(cpu_freq, "current", None),
    **ram,
}
print("Real detected hardware (this run, this machine):")
for k, v in hardware_detected.items():
    print(f"  {k}: {v}")

import shutil

disk = shutil.disk_usage(PROJECT_ROOT)
print(f"Project drive — total: {disk.total/1e9:.1f} GB, used: {disk.used/1e9:.1f} GB, "
      f"free: {disk.free/1e9:.1f} GB (real, measured now)")

# ## 2. Library Availability Check
# Each library is actually imported (not assumed present); a MISSING entry means it needs installing before any
# downstream notebook that depends on it will run.

import importlib

REQUIRED_LIBS = [
    "pandas", "numpy", "polars", "pyarrow", "sklearn", "xgboost", "lightgbm",
    "catboost", "networkx", "shap", "matplotlib", "seaborn", "scipy", "statsmodels", "openpyxl",
]

lib_report = {}
for lib in REQUIRED_LIBS:
    try:
        mod = importlib.import_module(lib)
        lib_report[lib] = getattr(mod, "__version__", "importable (no __version__ attr)")
    except ImportError as e:
        lib_report[lib] = f"MISSING — {e}"

print("Real import results (this environment, this run):")
for lib, status in lib_report.items():
    flag = "OK " if not str(status).startswith("MISSING") else "!! "
    print(f"  [{flag}] {lib}: {status}")

missing = [lib for lib, s in lib_report.items() if str(s).startswith("MISSING")]
if missing:
    print(f"\nACTION NEEDED before proceeding to BP notebooks — install: {', '.join(missing)}")
else:
    print("\nAll required libraries import cleanly.")

# ## 3. Real Per-Thread-Count Benchmark
# Spawns a fresh Python subprocess per thread count in `configs/resource_limits.yaml`'s
# `benchmark_thread_counts: [4, 8, 12, 16]`, each with its own `OMP_NUM_THREADS`/`OPENBLAS_NUM_THREADS`/
# `MKL_NUM_THREADS` set *before* numpy is imported in that subprocess (env vars set after numpy is already
# imported in *this* kernel have no effect on BLAS thread pools — this is exactly why a fresh subprocess per
# count is used, not an in-process env-var swap). Task: a 2000×2000 float64 matrix multiply, timed with
# `time.perf_counter()`. Real wall-clock numbers only — never a modeled/estimated curve.

import os
import subprocess

THREAD_ENV_VARS = ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"]
BENCHMARK_THREAD_COUNTS = [4, 8, 12, 16]  # from configs/resource_limits.yaml

BENCH_SCRIPT = (
    "import time, numpy as np\n"
    "rng = np.random.default_rng(42)\n"
    "a = rng.random((2000, 2000)); b = rng.random((2000, 2000))\n"
    "t0 = time.perf_counter()\n"
    "c = a @ b\n"
    "print(time.perf_counter() - t0)\n"
)

bench_results = {}
with timer("full thread-count benchmark sweep"):
    for n in BENCHMARK_THREAD_COUNTS:
        env = os.environ.copy()
        for var in THREAD_ENV_VARS:
            env[var] = str(n)
        proc = subprocess.run(
            [sys.executable, "-c", BENCH_SCRIPT],
            env=env, capture_output=True, text=True, timeout=120,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            elapsed = float(proc.stdout.strip())
            bench_results[n] = elapsed
            print(f"  threads={n:>2}: {elapsed:.4f}s (real, measured)")
        else:
            bench_results[n] = None
            print(f"  threads={n:>2}: FAILED — stderr: {proc.stderr[-300:]}")

print("\nRaw results dict (real):", bench_results)

# Real thermal pause after the heavy benchmark sweep above — genuine sleep, cadence user-confirmed 12s.
thermal_checkpoint(label="post hardware-benchmark sweep")

# ## 4. Write Real Benchmark Summary
# Every field below is pulled from the live variables computed in this run — nothing here is copied from a
# prior run or an assumed placeholder.

import json
from datetime import datetime, timezone

summary = {
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "project_root": str(PROJECT_ROOT),
    "warp_config": perf_config,
    "hardware_detected": hardware_detected,
    "library_versions": lib_report,
    "thread_count_benchmark_seconds": bench_results,
    "note": "All values above are measured on this run, on this machine — none are assumed or copied from configs/resource_limits.yaml's [ASSUMPTION]-flagged placeholders.",
}

out_path = PROJECT_ROOT / "logs" / "00_hardware_benchmark_summary.json"
out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w") as f:
    json.dump(summary, f, indent=2)

print(f"Real benchmark summary written to: {out_path}")
print(json.dumps(summary, indent=2)[:1500], "...")

# ## Next Step
# Once every library above imports cleanly and the benchmark summary looks sane for this machine, proceed to
# `notebooks/bp1_transaction_monitoring_detection/01_business_understanding_policy.ipynb` — BP1's first notebook.
# 
# If `configs/resource_limits.yaml`'s `[ASSUMPTION]`-flagged hardware fields (`cpu_max_boost_ghz`, `ram_speed_mhz`,
# `ssd_free_gb_approx`) differ from Section 1's real detected values above, update that YAML to match — this
# notebook's own detected numbers are the source of truth going forward, not the config file's placeholders.
