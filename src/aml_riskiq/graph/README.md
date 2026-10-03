# src/aml_riskiq/graph/
Honest placeholder. BP3 (Network Graph Intelligence) is this platform's one real graph-structural
capability -- a directly-interpretable RULE over structural signals (2-hop proximity to a known-flagged
account, account degree, component size -- see `reports/bp3_network_graph_intelligence/RULE_CARD.md`),
not a trained classifier (SHAP/LIME are genuinely N/A here, not merely omitted -- see that RULE_CARD's
own explicit statement). The real, saved rule artifact is
`models/bp3_network_graph_intelligence/bp3_notebook3_champion_rule_li_medium.json`.

Today, every real graph-structural computation lives in two places, neither of which is this directory:
- BP3's own Notebook 2/3 cells (`notebooks/bp3_network_graph_intelligence/02_...`, `03_...`), where the
  structural signals are actually computed from the real transaction graph.
- `src/aml_riskiq/serving/bp3_rule_scoring_service.py`, the deployed FastAPI service that applies the
  already-saved rule to a real account lookup at request time -- a rule-application service, not a
  general-purpose graph-computation library.

There is no shared, reusable graph-algorithms module (degree/PageRank/component-size helpers usable by
any BP) here yet. `src/aml_riskiq/features/README.md` already discloses graph-derived features (degree,
PageRank, component size) as a planned-but-not-yet-extracted capability for BP1 onward -- this directory
is where that logic would live once extracted, alongside BP3's own structural-rule logic. Also real and
disclosed: BP3's Docker image depends on
`models/bp3_network_graph_intelligence/bp3_notebook3_near_train_flagged_lookup_li_medium.parquet`, an
artifact not yet generated on this machine (see `ROADMAP.md` and
`scripts/check_docker_copy_paths.py`'s `KNOWN_PENDING_ARTIFACTS`).
