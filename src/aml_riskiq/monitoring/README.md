# src/aml_riskiq/monitoring

Shared production-monitoring module, built once and imported by every model-bearing BP (same
"built once, imported everywhere" pattern as `src/aml_riskiq/reporting/report_builder.py`).

- `drift_monitor.py` -- Population Stability Index (PSI) score-distribution drift detection.
  Standard industry verdict bands (PSI < 0.10 no shift, 0.10-0.25 moderate, > 0.25
  significant). Doesn't need real-time labels, unlike recall-based monitoring -- a real
  confirmed Is-Laundering label can lag live scoring by months.

First consumer: BP1 Notebook 3 (saves the real LI-Medium test-score baseline; demonstrates a
real train-vs-test PSI check as a proof the function works against this platform's own real
data, not just synthetic). Added 2026-09-30 as part of a corrections review -- no monitoring
module existed anywhere in this platform before this.
