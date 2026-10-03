# IBM AML RiskIQ Enterprise Suite

[![Institutional CI/CD & Compliance Pipeline](https://github.com/rnanda19/IBM_AML_RiskIQ_Enterprise_Suite/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/rnanda19/IBM_AML_RiskIQ_Enterprise_Suite/actions/workflows/ci.yml?query=branch%3Amain)
[![Regulatory Standard: SR 11-7 / OCC 2011-12](https://img.shields.io/badge/Regulatory-SR%2011--7%20%2F%20OCC%202011--12-0052CC.svg)](https://www.federalreserve.gov/supervisionreg/srletters/sr1107.htm)
[![Python 3.10 | 3.11](https://img.shields.io/badge/Python-3.10%20%7C%203.11-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Code Style: Ruff](https://img.shields.io/badge/Code%20Style-Ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Security: Bandit Audited](https://img.shields.io/badge/Security-Bandit%20Scanned-yellow.svg)](https://github.com/PyCQA/bandit)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

> **Institutional-Grade Anti-Money Laundering (AML) Transaction Monitoring, Graph Anomaly Detection, and Automated FinCEN SAR Drafting Platform.**

---

## Executive Overview

The **IBM AML RiskIQ Enterprise Suite** is an enterprise-scale transaction surveillance and regulatory reporting engine designed to meet Tier-1 global regulatory benchmarks, including **Federal Reserve SR 11-7**, **OCC 2011-12**, and **FATF Recommendations**.

Modern financial institutions process millions of daily transactions where illicit patterns account for less than 0.1% of volume. Conventional rules-only monitoring systems suffer from high false-positive rates (often >95%), straining investigative capacity. This platform implements a **dual-track detection architecture** combining deterministic regulatory rules (CTR and Structuring) with network graph cycle analysis and calibrated gradient-boosted ensembles (LightGBM/XGBoost), accompanied by explainable AI (SHAP) for automated narrative generation on FinCEN Suspicious Activity Reports (SAR).

---

## Enterprise System Architecture

```mermaid
flowchart TD
    subgraph INGESTION["1. High-Throughput Ingestion & Schema Guards"]
        A[Transaction Stream / ISO 20022] --> B[Decimal Rounding & Schema Validator]
        B --> C[Audit Data Store]
    end

    subgraph DUAL_ENGINE["2. Dual-Track Analytics Engine"]
        B --> D[Deterministic Rules Engine]
        B --> E[Graph Network Topology Engine]
        
        D -->|CTR >= $10k & Smurfing Flags| F[Rule Signal Aggregator]
        E -->|Directed Cycle & Fan-In Detection| G[Network Anomaly Aggregator]
    end

    subgraph ENSEMBLE["3. Calibrated ML Classifier"]
        F --> H[LightGBM / XGBoost Ensemble]
        G --> H
        H --> I[Calibrated Probability Scoring]
    end

    subgraph LEVEL2_TRIAGE["4. Regulatory Governance & SAR Generation"]
        I --> J{Risk Escalation Threshold}
        J -->|Risk Score < 0.85| K[Auto-Cleared / Audited]
        J -->|Risk Score >= 0.85| L[Level-2 Investigator Alert Workbench]
        L --> M[SHAP Waterfall Feature Attribution]
        M --> N[Automated FinCEN SAR Draft Narrative]
    end

    style INGESTION fill:#1f2937,stroke:#3b82f6,stroke-width:2px,color:#fff
    style DUAL_ENGINE fill:#1f2937,stroke:#8b5cf6,stroke-width:2px,color:#fff
    style ENSEMBLE fill:#1f2937,stroke:#10b981,stroke-width:2px,color:#fff
    style LEVEL2_TRIAGE fill:#1f2937,stroke:#ef4444,stroke-width:2px,color:#fff