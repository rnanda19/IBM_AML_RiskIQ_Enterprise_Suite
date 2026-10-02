# CHANGELOG -- BP2: Typology & Red-Flag Pattern Detection

## 2026-09-30T15:05:04.871603+00:00
Notebook 4 (Compliance-Impact Reporting & Packaging) real run. Primary variant LI-Medium: champion RandomForest, test macro-F1 0.4440, overall verdict PASS. Five-format executive package regenerated in C:\Users\rnand\Documents\IBM_AML_RiskIQ_Enterprise_Suite\reports\bp2_typology_redflag_detection\executive_package.

## 2026-09-30T15:07:28.843938+00:00
Notebook 4 (Compliance-Impact Reporting & Packaging) real run. Primary variant LI-Medium: champion RandomForest, test macro-F1 0.4440, overall verdict PASS. Five-format executive package regenerated in C:\Users\rnand\Documents\IBM_AML_RiskIQ_Enterprise_Suite\reports\bp2_typology_redflag_detection\executive_package.

## 2026-10-01T08:27:23.163655+00:00
Notebook 4 (Compliance-Impact Reporting & Packaging) real run. Primary variant LI-Medium: champion RandomForest, test macro-F1 0.4440, overall verdict PASS. Five-format executive package regenerated in C:\Users\rnand\Documents\IBM_AML_RiskIQ_Enterprise_Suite\reports\bp2_typology_redflag_detection\executive_package.

## 2026-10-01T18:59:12.751438+00:00
Hardening pass (Claude, on-device): investigated BP2 Notebook 3
(03_statistical_validation_deployment_SINGLE_CELL.py) to resolve the Dockerfile's
"ACTION NEEDED" comment. Found the real champion (RandomForest) does have one real,
disclosed NaN-prone feature column -- `amount_paid_received_ratio` (undefined whenever a
real row has Amount Received == 0, left as a real NaN per Lesson #7, never silently
imputed at feature-engineering time) -- and the real validation report JSON had no
impute-related key saved. Made a minimal, additive edit to Notebook 3's own report-dict
literal (just above the `champion_name` key) to persist `champion_needs_rf_impute` (bool)
and `rf_impute_value` (float, from the real `_train_median_full` Series the notebook
already computes for its own in-kernel impute step -- no new computation added), reusing
the exact key names BP4's own service already established on this platform for the
identical concept. Verified with `py_compile` and a re-cat of the surrounding lines.
NOTE: this report (bp2_notebook3_validation_report_li_medium.json) was generated before
this edit and does NOT yet contain the two new keys -- Notebook 3 needs ONE re-run
(DATASET_VARIANT='LI-Medium') before a fresh real report carries them and this Dockerfile's
image can actually serve real-valued impute logic.
Added `src/services/bp2_scoring_service.py`, mirroring BP1/BP4's service pattern: loads the
real champion pickle + real label encoder pickle + real validation report at import time;
multi-class `/score` response (`predicted_typology` via `LabelEncoder.inverse_transform`,
`confidence`, `class_probabilities`) since macro-F1/argmax has no single threshold (no
`is_flagged`/`threshold` fields, unlike BP1/BP4); conditional RandomForest NaN-impute path
gated on the new `champion_needs_rf_impute` flag, mirroring Notebook 3's own
`score_transaction` exactly. Env vars: `BP2_CHAMPION_MODEL_PATH`, `BP2_LABEL_ENCODER_PATH`,
`BP2_DATASET_VARIANT` (default `LI-Medium`), matching the Dockerfile's existing names.
Added `tests/bp2_typology_redflag_detection/test_bp2_scoring_service.py` (8 tests, synthetic
stub champion + stub label encoder only, never the real model): feature_cols/class_names
loaded from report, `/health`, `/score` shape, 422 on missing required feature, optional
NaN column omission still scores, RF-impute-applied and RF-impute-not-applied paths. Ran
`python3 -m pytest tests/bp2_typology_redflag_detection/test_bp2_scoring_service.py -v` --
8 passed, 0 failed.
Updated `src/docker/bp2_typology_redflag_detection/Dockerfile`'s own comment to mark the
"ACTION NEEDED" item RESOLVED (service now exists; impute logic awaits the one Notebook 3
re-run noted above). Confirmed via `grep`+`ls -la` that the Dockerfile's existing COPY
paths and ENV var names already match the real on-device filenames
(`bp2_notebook3_champion_li_medium.pkl`, `bp2_notebook3_label_encoder_li_medium.pkl`) --
no path edit was needed. Confirmed `docker-compose.yml`'s build context already reads
`../../..` (platform-wide fix applied earlier tonight) -- not re-touched here.
