# Model Registry

What's actually persisted on disk per business problem, and why BP3 and BP6 have no trained-model entry.
Model binaries themselves are gitignored (see `.gitignore` / `DATA_PRIVACY.md`) -- this table, plus the
live SHA-256 + mtime check every BP1/BP2/BP4/BP5 service exposes under its own `/health` endpoint (added
2026-10-02, `src/aml_riskiq/serving/_model_registry.py`), is how a champion artifact's identity is verified without
committing multi-megabyte binaries to git.

| BP | Persisted artifact (mandatory LI-Medium tier) | Champion | Real size | SHA-256 |
|---|---|---|---|---|
| BP1 | `models/bp1_transaction_monitoring_detection/bp1_notebook3_champion_li_medium.pkl` | XGBoost | 1,662,760 bytes | `500931694c9dfc84a2876f4732bcfe385756c5d4ff4b44ef7db53daaa22d0af2` |
| BP2 | `models/bp2_typology_redflag_detection/bp2_notebook3_champion_li_medium.pkl` | RandomForest | 24,723,702 bytes | `ce0d4b013313681d5bc7a43025ffcb33a56a3479bd55b38c08e1dfa88a1561b9` |
| BP3 | `models/bp3_network_graph_intelligence/bp3_notebook3_champion_rule_li_medium.json` | 2-hop proximity-to-flagged RULE (no trained model -- see `RULE_CARD.md`) | 2,957 bytes | `ca0fd5c1cc9ecfc97d85480afbddcaad9073b6069723f7b5715e553a74bf83c1` |
| BP4 | `models/bp4_structuring_smurfing_detection/bp4_notebook3_champion_li_medium.pkl` | XGBoost | 1,699,812 bytes | `2287d370d49d1a465bcd9fda4950f33f8a62806aba8cf0086dd5d4a257cd0751` |
| BP5 | `models/bp5_correspondent_banking_crossborder_risk/bp5_li_medium_model_v1.pkl` | XGBoost | 1,682,159 bytes | `e4a5908c3f4cee13456c7adc4e2653ca6b41de098565e0608e4f565a68178b0b` |
| BP6 | n/a -- pure rollup of BP1-BP5's own already-computed summary JSON, no model of its own | n/a | n/a | n/a |

All five hashes above were computed directly from the real on-disk files (`sha256sum`), not copied from a
report or carried forward from memory -- re-run `sha256sum` on the path in the table to reproduce them.

## Live verification
Every BP1/BP2/BP4/BP5 scoring service recomputes its own champion's SHA-256 (streamed, not loaded whole)
and its filesystem mtime fresh at import time and exposes both under `/health`'s `model_registry` key --
so a caller can confirm exactly which artifact a running container actually loaded, not just which
filename it was told to load. The report's own `generated_at_utc` is also surfaced where the real saved
validation report has that field (BP1's does; BP2/BP4/BP5's do not as of this writing) -- reported as
`null` where absent, never a fabricated substitute for a value the notebook never actually saved.

## HI-Small tier
BP1 and BP4 also have a real, independently-confirmed HI-Small-tier champion
(`bp1_notebook3_champion_hi_small.pkl`, `bp4_notebook3_champion_hi_small.pkl`), and BP5 has one under its
own naming (`bp5_hi_small_model_v1.pkl`) -- all omitted from the table above for brevity since the
mandatory tier for this platform is LI-Medium (see `PROJECT_STRUCTURE_LOCKED.md`); both tiers' full real
metrics are in `docs/evidence_ledger/EVIDENCE_LEDGER.md`.
