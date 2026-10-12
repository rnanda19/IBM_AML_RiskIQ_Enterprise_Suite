# Monitoring

## What's real today (`src/aml_riskiq/monitoring/`)
`drift_monitor.py` -- a real Population Stability Index (PSI) implementation, the standard industry
convention for score-distribution drift detection (PSI < 0.10 no shift, 0.10-0.25 moderate,
> 0.25 significant -- see the module's own docstring for why PSI rather than label-dependent recall
tracking: a real confirmed `Is-Laundering` label can lag live scoring by months). Built once, imported by
every model-bearing BP, following this platform's "build once, reuse everywhere" (HYPER) pattern already
established by `src/aml_riskiq/reporting/report_builder.py`. First real consumer: BP1 Notebook 3, which saves a real
train-vs-test score-distribution PSI check against its own LI-Medium test baseline.

## Input / data-quality monitoring (`src/aml_riskiq/monitoring/data_quality.py`, added 2026-10-12)
A second real monitoring module, built as a companion to `drift_monitor.py` rather than a replacement
for it. Where `drift_monitor.py` tracks drift in a model's *output score*, `data_quality.py` checks the
*input* side -- the things that typically break a model silently before its score drift would even show
it:

- `validate_input_schema()` -- missing/extra columns and dtype mismatches against an expected schema.
- `missing_value_report()` -- per-column missing-value counts and fractions.
- `out_of_range_report()` -- per-column out-of-range detection, with bounds derived from a baseline's own
  quantiles (not hardcoded thresholds).
- `feature_drift_report()` -- reuses the same PSI function from `drift_monitor.py`, applied per feature
  column instead of only to the final score, so a shift in one input feature can be caught even if it
  does not (yet) move the aggregate score distribution.
- `alert_volume_report()` -- flags an alert count for a period as anomalously high/low versus a baseline
  period (ratio-based, `ALERT_VOLUME_RATIO_LOW`/`ALERT_VOLUME_RATIO_HIGH`).
- `recommend_retraining_review()` -- combines whichever of the above signals are available into a single
  `recommend_review: bool` + `reasons: [...]` verdict. It never recommends automatic retraining -- only
  that a human reviews the model -- and it records which signals were unavailable (`missing_signals`)
  rather than silently treating an absent check as "passed."
- `build_input_quality_report()` -- assembles a dated report dict from the above. Its `baseline_is_synthetic`
  parameter has **no default**: every caller must say explicitly whether the comparison baseline is real
  production traffic or synthetic/self-check data, so a report can never silently imply live production
  monitoring it isn't actually doing.

**Current wiring: BP1 Notebook 3 only**, following the same "first real consumer" precedent
`drift_monitor.py` itself set. BP1's Notebook 3 computes a schema check, a missing-value report, an
out-of-range report (baseline = `X_train`, current = `X_test`), and a feature-level PSI report, combines
them via `recommend_retraining_review()`, and saves the result to
`reports/bp1_input_quality_report_<variant>.json` with `baseline_is_synthetic=True` -- X_train/X_test are
both real, held-out splits of the same synthetic Kaggle IBM-AML dataset this whole platform is built on,
so this is a genuine self-check that the reporting code runs correctly against this platform's own real
(if synthetic) data, **not** a live production-vs-production comparison. BP2/BP3/BP4/BP5 do not yet call
this module; extending the same wiring to their Notebook 3 scripts is recorded as open work in
`ROADMAP.md`, not silently assumed.

Both `drift_monitor.py` and `data_quality.py` are covered by real unit tests
(`tests/unit/test_drift_monitor.py`, `tests/unit/test_data_quality.py`) that exercise every public
function against synthetic pandas/numpy fixtures with hand-verified expected outputs -- these are tests of
the monitoring *code*, run in CI, not a live monitoring run against production traffic (there is none).

## What this is NOT (yet)
There is no live, continuously-running monitoring process, no `/metrics`-based drift/data-quality
exporter, and no alerting pipeline wired to either `drift_monitor.py` or `data_quality.py` -- both remain
library functions a notebook or a scheduled job would call, not services. Each BP1/BP2/BP4/BP5 scoring
service's `/health` endpoint does expose a real, freshly-computed model-registry fingerprint (SHA-256 +
mtime of the loaded artifact -- see `MODEL_REGISTRY.md`), every request across all 6 HTTP services emits a
structured audit-log line carrying a request-correlation ID (see `SECURITY.md`), and every HTTP service now
also exposes a real `/ready` endpoint distinct from `/health` (see `SECURITY.md`'s readiness section) --
together the closest this platform has to production observability today. Anything beyond that (a real
Prometheus exporter, a scheduled drift/data-quality job, alerting on `recommend_retraining_review()`
output, BP2-5 Notebook-3 wiring) is future work, tracked in `ROADMAP.md`, not claimed here as already
built.
