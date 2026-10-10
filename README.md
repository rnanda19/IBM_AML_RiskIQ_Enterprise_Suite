# IBM AML RiskIQ Enterprise Suite

[![CI](https://img.shields.io/github/actions/workflow/status/rnanda19/IBM_AML_RiskIQ_Enterprise_Suite/ci.yml?branch=main&label=CI&labelColor=2563EB)](https://github.com/rnanda19/IBM_AML_RiskIQ_Enterprise_Suite/actions/workflows/ci.yml)
[![Lint & Format](https://img.shields.io/github/actions/workflow/status/rnanda19/IBM_AML_RiskIQ_Enterprise_Suite/code-quality.yml?branch=main&label=Lint%20%26%20Format&labelColor=0D9488)](https://github.com/rnanda19/IBM_AML_RiskIQ_Enterprise_Suite/actions/workflows/code-quality.yml)
[![CodeQL Security Scan](https://img.shields.io/github/actions/workflow/status/rnanda19/IBM_AML_RiskIQ_Enterprise_Suite/codeql.yml?branch=main&label=CodeQL%20Security%20Scan&labelColor=7C3AED)](https://github.com/rnanda19/IBM_AML_RiskIQ_Enterprise_Suite/actions/workflows/codeql.yml)
[![Docker Build & Run Verification](https://img.shields.io/github/actions/workflow/status/rnanda19/IBM_AML_RiskIQ_Enterprise_Suite/docker-verify.yml?branch=main&label=Docker%20Build%20%26%20Run%20Verification&labelColor=B45309)](https://github.com/rnanda19/IBM_AML_RiskIQ_Enterprise_Suite/actions/workflows/docker-verify.yml)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg?labelColor=0891B2)]()
[![CRISP-DM](https://img.shields.io/badge/methodology-CRISP--DM-informational.svg?labelColor=CA8A04)]()
[![License: All Rights Reserved](https://img.shields.io/badge/license-All%20Rights%20Reserved-lightgrey.svg?labelColor=475569)](LICENSE)

**IBM AML RiskIQ Enterprise Suite** is a full-stack, production-grade anti-money-laundering and
financial-crime intelligence platform covering six independently validated Business Problems: transaction
monitoring, typology and red-flag classification, transaction-network and graph intelligence, structuring
and smurfing detection, correspondent-banking and cross-border wire risk, and enterprise-wide compliance
rollup reporting. Every BP is built end-to-end -- a real trained model or directly-interpretable rule, a
deployable FastAPI scoring service with API-key auth and audit logging, and a five-format executive
reporting package (HTML dashboard, Word report, Excel workbook, PowerPoint deck, PDF export) -- and is
grounded against real regulatory language from the Bank Secrecy Act, the USA PATRIOT Act, FinCEN SAR-filing
and red-flag-typology guidance, and real Federal Reserve / FinCEN enforcement actions. On this platform's
locked validation tier (LI-Medium), all six Business Problems pass their statistical validation gates; the
platform's real, assumption-labeled financial rollup totals **$13.88M** in false-positive-reduction
investigator-hours saved, **$97.95M** in illustrative regulatory-exposure-avoidance, and **$1.10M+** in
typology auto-confirmation value (see Business Problems below for the full real, per-BP breakdown).
Built on IBM's own published, open synthetic AML dataset -- see the Dataset section below for the full
citation.

## System Architecture

```mermaid
%%{init: {"theme": "base", "themeVariables": {
  "primaryColor": "#1e293b",
  "primaryTextColor": "#ffffff",
  "primaryBorderColor": "#64748b",
  "lineColor": "#1e293b",
  "fontSize": "17px",
  "fontFamily": "Segoe UI, Helvetica, Arial, sans-serif"
}}}%%
flowchart TD
    SRC(["IBM AML-Data · github.com/IBM/AML-Data · synthetic transactions"]):::source

    SRC ==> NB["Per-BP Notebooks<br/>01 Business Understanding → 02 Feature Eng + Modeling → 03 Statistical Validation → 04 Compliance Reporting"]:::stage

    NB ==> M1["BP1 model<br/>XGBoost"]:::model
    NB ==> M2["BP2 model<br/>RandomForest"]:::model
    NB ==> M3["BP3 signal<br/>Rule JSON"]:::model
    NB ==> M4["BP4 model<br/>XGBoost"]:::model
    NB ==> M5["BP5 model<br/>XGBoost"]:::model

    M1 ==> S1["bp1_scoring_service<br/>:8000"]:::service
    M2 ==> S2["bp2_scoring_service<br/>:8001"]:::service
    M3 ==> S3["bp3_rule_scoring_service<br/>:8003"]:::service
    M4 ==> S4["bp4_scoring_service<br/>:8001"]:::service
    M5 ==> S5["bp5_scoring_service<br/>:8002"]:::service

    SEC["_security.py<br/>API-key auth · rate-limit · audit log"]:::infra -.-> S1 & S2 & S3 & S4 & S5
    REG["_model_registry.py<br/>live SHA-256 + mtime under /health"]:::infra -.-> S1 & S2 & S4 & S5

    S1 & S4 & S5 ==> DOK["Docker: BP1 / BP4 / BP5<br/>build + run verified in CI"]:::docker
    S2 ==> DOKB2["Docker: BP2<br/>awaiting report refresh"]:::dockerwarn
    S3 ==> DOKW["Docker: BP3<br/>awaiting lookup artifact"]:::dockerwarn

    DOK ==> CI1["ci.yml<br/>lint + mypy + pytest (52 tests)"]:::ci
    DOK ==> CI2["code-quality.yml<br/>bandit + format"]:::ci
    DOK ==> CI3["codeql.yml<br/>weekly security scan"]:::ci
    DOK ==> CI4["docker-verify.yml<br/>build + poll /health"]:::ci

    NB ==> R1["MODEL_CARD.md / RULE_CARD.md<br/>per BP1 – BP5"]:::report
    R1 ==> R2["BP6 PLATFORM_CARD.md<br/>platform rollup, no model of its own"]:::report
    R2 ==> DOKB["Docker: BP6<br/>one-shot batch job, no port"]:::dockerwarn

    classDef source fill:#0ea5e9,stroke:#0369a1,color:#ffffff,stroke-width:3px,font-weight:bold
    classDef stage fill:#1d4ed8,stroke:#1e3a8a,color:#ffffff,stroke-width:3px,font-weight:bold
    classDef model fill:#7c3aed,stroke:#5b21b6,color:#ffffff,stroke-width:3px,font-weight:bold
    classDef service fill:#ea580c,stroke:#9a3412,color:#ffffff,stroke-width:3px,font-weight:bold
    classDef infra fill:#334155,stroke:#0f172a,color:#ffffff,stroke-width:2px,font-weight:bold,stroke-dasharray: 3 3
    classDef docker fill:#0d9488,stroke:#115e59,color:#ffffff,stroke-width:3px,font-weight:bold
    classDef dockerwarn fill:#64748b,stroke:#334155,color:#ffffff,stroke-width:3px,font-weight:bold,stroke-dasharray: 5 5
    classDef ci fill:#16a34a,stroke:#14532d,color:#ffffff,stroke-width:3px,font-weight:bold
    classDef report fill:#dc2626,stroke:#7f1d1d,color:#ffffff,stroke-width:3px,font-weight:bold

    linkStyle default stroke:#1e293b,stroke-width:2.5px
```

Every box above is a real, committed component of this repository -- there is no hosted/live deployment layer
yet (see `ROADMAP.md`). Three of the six BPs' Docker images are disclosed as not yet end-to-end verified:
**BP2** crashes on startup (its committed validation report predates a hardening edit that added two keys
the service now requires -- fix is a real notebook re-run, not a patch); **BP3** depends on an artifact
(`*_near_train_flagged_lookup_*.parquet`) this platform has not yet generated; **BP6** has no port/`/health`
endpoint to poll (it is a one-shot report job, not a scoring API). See `ROADMAP.md`,
`scripts/check_docker_copy_paths.py`, and `.github/workflows/docker-verify.yml` for exactly how each is
scoped.

## Table of Contents
- [Dataset](#dataset)
- [Methodology](#methodology)
- [Business Problems](#business-problems-6---finalized-real-ground-truth-verified)
- [Repository Structure](#repository-structure)
- [How to Run](#how-to-run)
- [Engineering & Testing](#engineering--testing)
- [Status](#status)
- [Execution boundary](#execution-boundary-standing-rule)
- [Storage location](#storage-location-strict)
- [License](#license)

## Dataset
Published by IBM at **[github.com/IBM/AML-Data](https://github.com/IBM/AML-Data)** (IBM's own
documentation/index page for this dataset); the real data files are directly downloadable from
**[Kaggle: IBM Transactions for Anti-Money Laundering (AML)]
(https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml)**, the
dataset's real, direct download location, with the same files also mirrored on **IBM's own Box storage:
[ibm.box.com/v/AML-Anti-Money-Laundering-Data](https://ibm.box.com/v/AML-Anti-Money-Laundering-Data)**.
Generated by IBM using a multi-agent virtual-world simulation -- per IBM's own README: "the model and data
are NOT based on obfuscating or anonymizing real individuals. Everything is synthetic." No real account
holder, real transaction, or real financial institution is represented anywhere in this dataset or in this
repository's outputs. Also described in IBM Research's own paper: Altman et al., "Realistic Synthetic
Financial Transactions for Anti-Money Laundering Models," NeurIPS 2023 Datasets & Benchmarks track
([arXiv:2306.16424](https://arxiv.org/abs/2306.16424)). The dataset itself is released under the
CDLA-Sharing-1.0 license (distinct from the GitHub index page's own Apache-2.0 license -- see IBM's own
README for that distinction). See `DATA_PRIVACY.md` for the full data-handling policy, including exactly
what raw data is deliberately excluded from this repo and why.

## Methodology
Built under **CRISP-DM**: each BP's notebook lifecycle maps directly to the 6 standard stages (Business
Understanding -> Data Preparation -> Modeling -> Evaluation -> Deployment), with a compliance-specific
reporting stage layered on top (Notebook 4). Delivered **Agile**: each Business Problem is its own
sprint-sized, independently validated unit of work -- one BP finished and gated (see the 6-Gate SOP below)
before the next starts, never all six built in parallel with nothing finished. Every headline finding is
framed **SMART** (Specific - a named real metric; Measurable - a real computed number; Achievable -
grounded in what the dataset can actually support; Relevant - tied to a real regulatory or operational
driver; Time-bound - framed against a stated reporting period) -- see any BP's own `MODEL_CARD.md` for a
worked example. Two runtime-engineering disciplines run underneath: **WARP** (runtime resource governance
-- CPU/memory/thermal ceilings enforced per `configs/resource_limits.yaml`, preventing a long notebook run
from overheating or starving the host machine) and **HYPER** (delivery-acceleration techniques -- a shared
`src/aml_riskiq/` component library built once and imported everywhere, parametric per-BP YAML configs,
parallel CI jobs).

A 6-Gate SOP (Business Understanding -> Data Preparation -> Modeling -> Statistical Validation ->
Deployment -> Production Packaging/Governance) and a per-BP Evidence Ledger
(`docs/evidence_ledger/EVIDENCE_LEDGER.md`) gate every real metric before it is reported anywhere in this
repository -- zero-fabrication is the standing rule throughout (see `DATA_PRIVACY.md` and the Execution
boundary section below). See `LESSONS_LEARNED_APPLIED.md` for the specific real engineering bugs this
structure and its conventions were built to catch.

## Business Problems (6) - finalized, real-ground-truth-verified
Six independently validated Business Problems, each with real ground truth in the dataset (never a proxy
label) and a full five-format executive reporting package. **00 -- Executive Rollup Summary** (BP6) is the
platform-wide reconciliation and leads the list; BP1-BP5 follow in numbered order. Every row is PASS on
this platform's locked mandatory realism-validation tier (LI-Medium) -- see `BENCHMARKS.md` for the full
real baseline-vs-model comparison and `docs/evidence_ledger/EVIDENCE_LEDGER.md` for the single source of
truth every figure below is drawn from. Naming cross-checked against real primary-source terminology from
a Federal Reserve consent order (American Express Bank International) and a FinCEN civil money penalty
assessment (JPMorgan Chase).

### [00 -- Executive Rollup Summary](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp6/BP6_Platform_Rollup_Dashboard.html)
Pure rollup of BP1-BP5's own already-computed real figures -- no model of its own, verdict **PASS** on its
reconciliation gate. Real platform-wide financial rollup (3 categories, never blended): false-positive-
reduction savings across BP1+BP4+BP5 **$13.88M** (213,496 investigator hours); true-positive illustrative
regulatory-exposure-avoidance across BP1+BP4+BP5 **$97.95M** (+1,959 cases); BP2's own typology auto-
typing/confirmation value **$1,313 + $1.10M**, kept separate (different unit basis). Every dollar figure is
an explicitly labeled ASSUMPTION -- see `reports/bp6_enterprise_compliance_monitoring/PLATFORM_CARD.md`.
**Reports:** [Live Dashboard](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp6/BP6_Platform_Rollup_Dashboard.html) &middot; [Word Report](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp6/BP6_Platform_Rollup_Report.docx) &middot; [Excel Workbook](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp6/BP6_Platform_Rollup_Workbook.xlsx) &middot; [PowerPoint Deck](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp6/BP6_Platform_Rollup_Deck.pptx) &middot; [PDF Export](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp6/BP6_Platform_Rollup_Report.pdf)

### [BP1 -- Transaction Monitoring & Suspicious Activity Detection](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp1/BP1_Compliance_Impact_Dashboard.html)
Real ground truth: `Is Laundering`. Champion **XGBoost**, Test PR-AUC **0.1242**, verdict **PASS**. The real
function institutions themselves call a "transaction monitoring system" -- language drawn from a real
Federal Reserve consent order and FinCEN's own civil-money-penalty language. Deployed, stops review of
294,907 real false-positive alerts (**$4.79M** investigator-hours saved) while independently catching 319
more real laundering cases (**$15.95M** illustrative regulatory-exposure-avoidance).
**Reports:** [Live Dashboard](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp1/BP1_Compliance_Impact_Dashboard.html) &middot; [Word Report](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp1/BP1_Compliance_Impact_Report.docx) &middot; [Excel Workbook](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp1/BP1_Compliance_Impact_Workbook.xlsx) &middot; [PowerPoint Deck](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp1/BP1_Compliance_Impact_Deck.pptx)

### [BP2 -- Typology & Red-Flag Pattern Detection](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp2/BP2_Compliance_Impact_Dashboard.html)
Real ground truth: `Patterns.txt`'s block-structured typology labels (up to 8 typologies -- fan-out,
fan-in, gather-scatter, scatter-gather, cycle, random, bipartite, stack). Champion **RandomForest**, Test
macro-F1 **0.4440**, verdict **PASS**. Matches FinCEN's own "red flags" typology-indicator language.
Deployed, auto-classifies 101 more real cases by typology (**$1,313** saved) and independently confirms the
correct typology on 138 real cases a single-typology heuristic would miss (**$1.10M** confirmation value).
**Reports:** [Live Dashboard](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp2/BP2_Compliance_Impact_Dashboard.html) &middot; [Word Report](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp2/BP2_Compliance_Impact_Report.docx) &middot; [Excel Workbook](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp2/BP2_Compliance_Impact_Workbook.xlsx) &middot; [PowerPoint Deck](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp2/BP2_Compliance_Impact_Deck.pptx)

### [BP3 -- Transaction Network & Graph Intelligence](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp3/BP3_Compliance_Impact_Dashboard.html)
No trained model needed -- real account-to-account structure only, no proxy label required. Champion
signal: 2-hop proximity to a TRAIN-flagged account, real network-lift ratio **3.19x** over a 1.157% base
rate (bootstrap 95% CI [3.157x, 3.219x]), verdict **PASS**, on a real graph of 2,032,095 nodes / 4,363,197
edges. Hands investigators a real bounded 2-hop ego-network around every flagged account instead of
reviewing it in isolation -- no dollar figure claimed; no sourced real per-account investigation-cost basis
exists for this BP (disclosed honestly in `RULE_CARD.md`, never invented).
**Reports:** [Live Dashboard](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp3/BP3_Compliance_Impact_Dashboard.html) &middot; [Word Report](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp3/BP3_Compliance_Impact_Report.docx) &middot; [Excel Workbook](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp3/BP3_Compliance_Impact_Workbook.xlsx) &middot; [PowerPoint Deck](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp3/BP3_Compliance_Impact_Deck.pptx)

### [BP4 -- Structuring & Smurfing Detection](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp4/BP4_Compliance_Impact_Dashboard.html)
Targets a named federal crime (31 U.S.C. SS5324). Champion **XGBoost**, Test PR-AUC **0.1253**, verdict
**PASS** -- the platform's highest real recall among its three binary BPs. Deployed, contributes the
platform's single largest real dollar figure: **$65.00M** illustrative regulatory-exposure-avoidance from
1,300 additional real structuring cases caught, plus **$4.23M** false-positive-reduction savings (65,120
investigator hours).
**Reports:** [Live Dashboard](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp4/BP4_Compliance_Impact_Dashboard.html) &middot; [Word Report](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp4/BP4_Compliance_Impact_Report.docx) &middot; [Excel Workbook](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp4/BP4_Compliance_Impact_Workbook.xlsx) &middot; [PowerPoint Deck](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp4/BP4_Compliance_Impact_Deck.pptx)

### [BP5 -- Correspondent Banking & Cross-Border Wire Risk](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp5/BP5_Compliance_Impact_Dashboard.html)
Targets the risk area behind real HSBC, Standard Chartered, and Danske Bank enforcement actions. Champion
**XGBoost**, Test PR-AUC **0.1399** (the platform's highest), verdict **PASS**, using 27 real features --
the most of any binary BP. Deployed, delivers the platform's single largest real false-positive-reduction
figure: **$4.85M** savings (74,649 investigator hours), plus **$17.00M** illustrative regulatory-exposure-
avoidance from 340 additional real cross-border cases caught.
**Reports:** [Live Dashboard](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp5/BP5_Compliance_Impact_Dashboard.html) &middot; [Word Report](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp5/BP5_Compliance_Impact_Report.docx) &middot; [Excel Workbook](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp5/BP5_Compliance_Impact_Workbook.xlsx) &middot; [PowerPoint Deck](https://rnanda19.github.io/IBM_AML_RiskIQ_Enterprise_Suite/bp5/BP5_Compliance_Impact_Deck.pptx)

Four BPs from the original 8-BP scaffold were dropped on review: Account/Entity AML Risk Scoring and Alert
Escalation/SAR-Filing Prediction both lack an independent ground-truth label in this dataset (proxy-only);
GenAI SAR Narrative Assistant is a generation task with nothing to validate output against; Alert
Prioritization is a composite/policy layer, not an independently trained model. See
`PROJECT_STRUCTURE_LOCKED.md` for the full naming history.

**One-time setup required before any "Live Dashboard" link above actually resolves:** a repo admin sets
Settings -> Pages -> Build and deployment -> Source to "GitHub Actions" -- `.github/workflows/pages.yml`
(backed by `scripts/build_pages_site.py`, a pure copy of the already-committed
`reports/<bp>/executive_package/` files, nothing regenerated) cannot flip that setting for itself. Until
then, every format is still reachable directly from this repository under each BP's own
`reports/<bp>/executive_package/` folder.

## Repository Structure
See `PROJECT_STRUCTURE_LOCKED.md` for the authoritative folder layout and the rule that it does not get
renamed or reorganized once notebooks start writing paths into it. At a glance:

| Path | Contents |
|---|---|
| `notebooks/` | `00_hardware_benchmark/` + one folder per BP; each BP is 4 real single-cell scripts (BP6 is 1 consolidated `.ipynb`) |
| `src/aml_riskiq/{serving,features,reporting,monitoring,utils,models,typology}/` | Shared component library -- FastAPI scoring services, feature engineering, report building, drift monitoring |
| `src/aml_riskiq/{ingestion,graph,explainability}/` | Honest placeholders -- real logic (data loading, BP3's graph-structural rule, BP1/BP2/BP4/BP5's already-computed SHAP/LIME) currently lives inline per-notebook, not yet extracted into these modules (see each one's own README.md) |
| `src/docker/` | One `Dockerfile` + `docker-compose.yml` + `.dockerignore` per BP |
| `tests/` | `unit/` (pure-logic tests) + `integration/` (one folder per BP), pytest (52 tests, all passing) |
| `models/` | Trained artifacts per BP -- gitignored by default; the 6 small champion files `MODEL_REGISTRY.md` documents by SHA-256 are committed as an exception |
| `reports/` | `MODEL_CARD.md`/`RULE_CARD.md`/`PLATFORM_CARD.md` + `CHANGELOG.md` per BP |
| `configs/` | Per-BP YAML + resource-limit (WARP) ceilings |
| `docs/` | Evidence Ledger, compliance mapping, data dictionary |
| `.github/` | CI workflows, issue/PR templates, CODEOWNERS, Dependabot |
| `linkedin/` | Portfolio-publishing packaging notes |

## How to Run
```bash
# install
pip install -r requirements.txt
pip install -e .

# run the real test suite (52 tests)
make test              # or: pytest tests/ -v

# full local quality gate (lint + mypy + bandit + test)
make test-all

# run a single scoring service locally (BP1 shown; see each BP's own Dockerfile for its port)
uvicorn src.aml_riskiq.serving.bp1_scoring_service:app --reload --port 8000
curl http://localhost:8000/health

# build + run a service's real Docker image
docker compose -f src/docker/bp1_transaction_monitoring_detection/docker-compose.yml up --build
```
Every `/score` endpoint is open-mode by default (no key required) and switches to enforced API-key auth the
moment `AML_RISKIQ_API_KEYS` is set in the environment -- see `SECRETS_MANAGEMENT.md` and `.env.example`.

## Engineering & Testing
- **Tests:** 52/52 passing (`pytest tests/`), covering all 5 FastAPI scoring services plus the shared
  `_security.py`/`_model_registry.py` modules (real 429 rate-limit and 401/200 auth integration tests, not
  mocked).
- **Type checking:** `mypy src/` -- 0 errors across 15 source files.
- **Security scanning:** `bandit -r src/` -- 0 blocking findings, 7 low-severity baseline (see `SECURITY.md`);
  CodeQL runs weekly + on every push/PR.
- **Hardening:** API-key authentication, per-route rate limiting (`slowapi`), and structured JSON audit
  logging on every scoring request -- added across BP1/BP2/BP4/BP5 in the 2026-10-02 hardening pass.
- **Model registry:** every running service recomputes its own champion model's SHA-256 (streamed) and
  filesystem mtime at import time and exposes both under `/health` -- see `MODEL_REGISTRY.md`.
- **Docker:** a real, permanent regression guard (`scripts/check_docker_copy_paths.py`, wired into CI)
  caught and fixed a genuine bug where 5 of 5 Dockerfiles never copied their required validation-report JSON
  into the image.

## Status
BP1, BP2, BP3, BP4, and BP5 have each completed real validation and passed both the structural and
statistical-robustness gates on their mandatory LI-Medium tier; BP6's platform-wide rollup passes its own
reconciliation gate as a pure pass-through of those five verdicts. All 5 FastAPI scoring services are
hardened (auth/rate-limit/audit-log) and covered by a passing 52-test suite. See
`docs/evidence_ledger/EVIDENCE_LEDGER.md` for the single source of truth and `ROADMAP.md` for what remains
(BP3's pending lookup-parquet artifact, live Docker build verification in CI, and GitHub publication --
now complete).

## Execution boundary (standing rule)
Claude generates notebooks and src/ modules only, and never executes the real data-processing pipeline itself.
You run every notebook on your own machine; all real numbers, charts and verdicts come from your own reported run.

## Storage location (strict)
Every file for this project - notebooks, src/ modules, trained-model artifacts, reports, configs, the
GitHub/LinkedIn packaging folders, everything - lives inside this one folder tree, under
`C:\Users\rnand\Documents\IBM_AML_RiskIQ_Enterprise_Suite\`, and nowhere else on this laptop.
Nothing for this project is written to Downloads, the home directory, or any other path.

## License
All Rights Reserved -- this repository is shared publicly for portfolio and demonstration purposes only. It
is not licensed for reuse, modification, or redistribution; see `LICENSE` for details.

---
Built by [Nandagopal](https://github.com/rnanda19).
