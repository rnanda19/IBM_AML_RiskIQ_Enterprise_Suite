# src/aml_riskiq/explainability/
Honest placeholder -- but unlike `ingestion/` and `graph/`, the real computation this module would wrap
already exists and is already real, not aspirational. Every trained-model BP (BP1, BP2, BP4, BP5) has a
real, already-run explainability step in its own Notebook 3
(`notebooks/bp<n>_*/03_statistical_validation_deployment_SINGLE_CELL.py`):

- **SHAP** (TreeExplainer, global importance) -- e.g. BP1 ranks `Payment Format` as the dominant real
  driver on LI-Medium; BP2 ranks `receiver_distinct_counterparties_to_date`; BP4 ranks
  `amount_to_rolling_window_mean_ratio`; BP5 ranks `sender_country_empirical_risk`. See each BP's own
  `reports/bp<n>_*/MODEL_CARD.md` for the real, saved values -- none of the figures above are re-derived
  or guessed here, they are read directly from that BP's own validation report.
- **LIME** (local, per real true-positive / predicted-typology instance) -- saved per case alongside the
  SHAP output.

**BP3 is a genuine, documented exception, not a gap:** it has no trained model, so SHAP/LIME are N/A by
design -- see `reports/bp3_network_graph_intelligence/RULE_CARD.md`'s own explicit statement. BP6 is a
pure rollup of BP1-BP5's own figures and likewise has no model of its own to explain.

## What's missing
This explainability logic currently lives entirely inside each BP's own Notebook 3 cell -- there is no
shared, importable module here that a scoring service could call at request time to produce a live
per-prediction SHAP/LIME explanation (today's `/score` endpoints return a probability and a threshold
decision, not a live explanation). Extracting a shared `explainability/` module -- and optionally wiring
a `/explain` endpoint into BP1/BP2/BP4/BP5's services -- is real, disclosed future work, not something
this directory already does.
