---
name: Model / rule improvement
about: Propose a change to a BP's champion model, feature set, or validation methodology
title: "[MODEL] "
labels: model-improvement
assignees: ""
---

## Business Problem
Which BP is this for (BP1-BP6)? Current champion (from that BP's MODEL_CARD.md/RULE_CARD.md):

## Current real metric (cite the source file)
e.g. "BP4 LI-Medium: XGBoost, test PR-AUC 0.1253 (reports/bp4_structuring_smurfing_detection/MODEL_CARD.md)"

## Proposed change
Feature addition/removal, candidate algorithm, hyperparameter range, threshold-selection method, etc.

## Expected real impact
How would this be measured? Which real metric should move, and on which mandatory validation tier (LI-Medium unless stated otherwise)?

## Leakage / governance check
- [ ] Confirmed this does not introduce train/test leakage (Lesson #11)
- [ ] Confirmed this does not silently change the two-gate verdict criteria after seeing a result (Lesson #15)
- [ ] Confirmed PR-AUC (or this BP's primary metric) remains the champion-selection criterion, not ROC-AUC alone

## Zero-fabrication check
All real numbers in this proposal's eventual resolution must come from an actual re-run on real data -- no illustrative/placeholder figures.
