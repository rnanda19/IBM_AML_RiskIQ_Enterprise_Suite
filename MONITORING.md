# Monitoring

## What's real today (`src/aml_riskiq/monitoring/`)
`drift_monitor.py` -- a real Population Stability Index (PSI) implementation, the standard industry
convention for score-distribution drift detection (PSI < 0.10 no shift, 0.10-0.25 moderate,
> 0.25 significant -- see the module's own docstring for why PSI rather than label-dependent recall
tracking: a real confirmed `Is-Laundering` label can lag live scoring by months). Built once, imported by
every model-bearing BP, following this platform's "build once, reuse everywhere" (HYPER) pattern already
established by `src/aml_riskiq/reporting/report_builder.py`. First real consumer: BP1 Notebook 3, which saves a real
train-vs-test score-distribution PSI check against its own LI-Medium test baseline.

## What this is NOT (yet)
There is no live, continuously-running monitoring process, no `/metrics` endpoint, and no alerting
pipeline -- `drift_monitor.py` is a library function a notebook or a scheduled job would call, not a
service. Each BP1/BP2/BP4/BP5 scoring service's `/health` endpoint does expose a real, freshly-computed
model-registry fingerprint (SHA-256 + mtime of the loaded artifact -- see `MODEL_REGISTRY.md`) and every
request across all 5 services emits a structured audit-log line (see `SECURITY.md`), which is the closest
this platform has to production observability today. Anything beyond that (a real Prometheus exporter, a
scheduled drift job, alerting) is future work, not claimed here as already built.
