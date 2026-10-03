# Project Structure - LOCKED as of 2026-09-29 (re-locked; supersedes the 2026-09-21 version below)

This folder layout is final as of the date above. Do not rename, move, or reorganize any folder here once a
notebook has written a path into a config file or a summary JSON.

## Why this is a hard rule (real, not hypothetical)
This project's own BP folders were renamed once already, on 2026-09-29 (8-BP scaffold -> 6-BP scaffold,
after the finalized business-problem scope was confirmed) - safe only because no notebook had yet written a
path referencing the old names, per Rule 1 below. Any FUTURE rename does not get that same free pass.

On the the prior credit-risk platform platform, a mid-project folder reorg (Phase 1 restructuring) left old notebooks and their
already-generated summary JSONs pointing at stale paths. This caused a chain of real bugs across multiple
notebooks (Notebook 27 Error 1/2, Notebook 34/35's path-resolution bugs) and forced a 3-then-4-candidate
path-resolver workaround (current nested path -> PILLAR_DIRS lookup -> legacy root path -> exact summary-JSON
path) that had to be retrofitted into every downstream notebook. On that prior lending-risk platform, project_config.json's own
`pillar_dirs` dict was discovered to still hold pre-reorg paths for every pillar that existed before a folder
move - only pillars created fresh after the move were safe to trust. Both cost real debugging hours.

## Standing rule for this project
1. This structure is decided once, here, before Sprint 1 starts. No BP folder gets renamed after its first
   notebook is written.
2. If a genuine restructure is ever unavoidable, every path written into any `configs/*.yaml` or
   `*_summary.json` must be regenerated, not left stale - never patch downstream notebooks with a
   multi-candidate path resolver as a substitute for fixing the source config.
3. Every notebook resolves its own project root via an environment-variable override first, then a bounded
   upward walk from the notebook's own location - never a hardcoded absolute path.

## Top-level layout
- docs/ - BRD, FRD, RTM, architecture, data dictionary, Evidence Ledger, compliance/regulatory mapping, the
  master plan (not yet written)
- data/{raw,processed,external} - gitignored; raw AML transaction extracts live here, once, never duplicated
- notebooks/ - 00_hardware_benchmark + one folder per BP (bp1_... through bp8_...)
- src/{typology,features,models,reporting,utils} - the shared HYPER component library, imported from BP1 onward
- tests/ - shared/ plus one folder per BP, pytest
- models/ - trained artifacts per BP (gitignored binaries; folder structure tracked)
- reports/ - MODEL_CARD.md + CHANGELOG.md per BP
- powerbi/{gold_tables,pbix} - BP8's decision/regulatory-reporting layer
- configs/ - per-BP YAML + resource_limits.yaml (WARP ceilings)
- .github/workflows/ - CI (lint, test, notebook-syntax-check, pre-commit)
- logs/ - gitignored run logs
- github_repo/ - staged packaging copy for the public GitHub push (see its own README.md for why this is
  separate from the working folders above)
- linkedin/ - portfolio post drafts

## BP folder naming (final as of 2026-09-29 - do not change without regenerating every configs/*.yaml)
bp1_transaction_monitoring_detection, bp2_typology_redflag_detection, bp3_network_graph_intelligence,
bp4_structuring_smurfing_detection, bp5_correspondent_banking_crossborder_risk, bp6_enterprise_compliance_monitoring

Real-world naming verified against primary sources (Federal Reserve consent order re: American Express Bank
International; FinCEN civil money penalty assessment re: JPMorgan Chase; JPMorgan Chase's own Global Financial
Crimes Compliance page) - BP1 maps to "transaction monitoring system" / "computer monitoring system", BP2 maps
to "red flags" (JPMorgan's own term for typology indicators). Dropped from the original 8-BP scaffold: Account
Risk Scoring (proxy-labeled only, no independent ground truth in accounts.csv), Alert Escalation/SAR-Filing
Prediction (no independent SAR-filed/not-filed label exists in this dataset), GenAI SAR Narrative Assistant
(a generation task, not independently validated against a ground-truth label), Alert Prioritization (a
composite/policy layer, not an independently trained model). Added: Structuring/Smurfing Detection and
Correspondent Banking/Cross-Border Wire Risk - both dataset-supported (real amount/timing and real
From Bank/To Bank + country-tagged accounts.csv fields) and both real, high-priority named functions at
top-tier banks.

[RESOLVED] The 2026-09-21 scaffold's BP naming was flagged as an unconfirmed proposed default. It has since
been reviewed problem-by-problem against real dataset ground-truth availability and cross-checked against real
AML terminology - this is now the confirmed, final structure.
