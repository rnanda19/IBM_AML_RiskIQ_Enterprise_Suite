# Model Risk Governance

Consolidates intended use, prohibited uses, versioning/rollback, and change approval for every trained
artifact in this platform (BP1/BP2/BP4/BP5's champion models, BP3's rule). Companion to
`MODEL_REGISTRY.md` (what is persisted and its live fingerprint) -- this document is about *how the
platform's models may and may not be used*, not what's on disk.

## Intended use

Every model and rule in this platform is a **portfolio demonstration of AML analytics methodology**,
trained and validated exclusively on the IBM synthetic Transactions for Anti-Money-Laundering dataset
(see `DATA_PRIVACY.md` for the real source). Intended use:
- Demonstrating detection methodology (feature engineering, imbalanced-classification evaluation,
  graph-based network scoring, explainability) against a known, labeled synthetic dataset.
- A reference implementation of an AML scoring-service architecture (API design, auth, rate limiting,
  audit logging, CI/Docker verification) that a real deployment could be modeled on.
- Portfolio and interview evidence of end-to-end AML analytics engineering capability.

## Prohibited uses

- **Scoring real customer or transaction data of any kind.** No champion model in this repository has
  been trained, validated, or calibrated on real bank data. Doing so would be a real compliance and data
  protection violation, independent of model quality.
- **Presenting any reported metric (PR-AUC, recall, F1, lift, or any dollar figure) as evidence of
  real-bank detection performance or real cost savings.** Every number in `BENCHMARKS.md` is reported
  against the IBM synthetic dataset's own held-out test split; see the "Real-world banking validation"
  gap already disclosed in this project's external benchmark review.
- **Using any single BP's output as the sole basis for a filing, escalation, or account action.** This
  platform has no investigator case-management workflow, no human-in-the-loop review step, and no
  SAR-filing capability (a GenAI SAR-narrative-assistant concept was evaluated and explicitly dropped
  earlier in this project's history -- see `docs/evidence_ledger/EVIDENCE_LEDGER.md`'s "Retired" section
  -- specifically because it would lack ground truth to validate against).
- **Treating BP3's output as a trained model's prediction.** BP3's champion is a deterministic 2-hop
  proximity-to-flagged rule, not a fitted classifier (see `RULE_CARD.md`) -- it carries none of the
  probabilistic calibration properties a trained model would.

## Model limitations (consolidated from each BP's own MODEL_CARD.md)

- Synthetic-data training: no model has seen real transaction behavior, real adversarial evasion
  patterns, or real investigator feedback.
- Low recall at the evaluated thresholds for BP1 (17.93%) and BP5 (18.30%) -- the majority of positive
  cases in each test population are missed at the currently reported operating point (see `BENCHMARKS.md`).
- No fairness/demographic-parity testing has been performed (already disclosed; see this project's
  external benchmark review and `DATA_PRIVACY.md`).
- No sanctions-list screening integration exists in this platform.
- BP2's and BP3's Docker-deployable services are currently non-functional (see `docs/audit/DEFECT_REGISTER.md`
  DEF-001/DEF-002) -- neither should be considered deployment-ready until their respective real notebook
  re-runs regenerate the missing artifacts.

## Versioning and rollback

- Every champion artifact's identity is verified live, not just by filename: each BP1/BP2/BP4/BP5
  scoring service recomputes its own loaded artifact's SHA-256 (streamed) and filesystem mtime at
  startup and exposes both under `/health`'s `model_registry` key (see `MODEL_REGISTRY.md`).
- **Promotion**: a new champion is promoted by replacing the `.pkl`/`.json` file at the path
  `MODEL_REGISTRY.md` documents for that BP, re-running that BP's `03_statistical_validation_deployment`
  gate to confirm it still passes its documented PASS/FAIL criteria, and updating the SHA-256 in
  `MODEL_REGISTRY.md` to match (the live `/health` fingerprint will then match the registry's recorded
  value again).
- **Rollback**: because gitignored model binaries are not themselves versioned in git history the way
  code is, rollback today means restoring the previous artifact file from wherever it was archived before
  promotion (e.g. a prior Docker image layer, or a backup copy kept outside the repo) and confirming the
  restored file's SHA-256 matches a previously recorded `MODEL_REGISTRY.md` entry. There is currently no
  automated one-command rollback mechanism -- this is a real, open gap, not a built capability being
  described optimistically.

## Change approval

- Any change to a committed champion artifact, or to the `ASSUMPTIONS` dict in any BP's
  `04_compliance_impact_reporting_packaging_SINGLE_CELL.py` (the three disclosed constants behind every
  dollar figure -- see `docs/business_value/BUSINESS_VALUE_METHODOLOGY.md`), is a change to this
  platform's reported results and should be reviewed as such: re-run that BP's full notebook sequence,
  regenerate its validation report and executive package, and update `BENCHMARKS.md`/`CHANGELOG.md` in
  the same change.
- Any change to `src/aml_riskiq/serving/_security.py` (shared by all 5 scoring services) should run the
  full `tests/unit/test_security.py` suite plus every service's own integration test file before merge,
  since a regression here affects every service identically (the HYPER "build once, reuse everywhere"
  pattern this module follows cuts both ways).

## Explicitly out of scope for this document

This is a portfolio-project governance document, not a claim of compliance with any specific regulatory
framework (SR 11-7, OCC 2011-12, or otherwise). No certification, attestation, or regulatory review has
been performed or is claimed.
