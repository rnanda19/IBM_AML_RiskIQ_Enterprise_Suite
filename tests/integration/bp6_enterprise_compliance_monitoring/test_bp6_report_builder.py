"""
Structural / wiring tests for BP6's own code path in the shared
src/aml_riskiq/reporting/report_builder.py -- the write_platform_html_dashboard /
compute_platform_status / build_platform_benefit_table /
generate_platform_smart_recommendations / build_bp_business_narratives_platform
functions BP6's Notebook 4 calls.

Scope discipline (same convention as every other BP's test file in this project):
this is a SYNTHETIC fixture -- small, clearly-invented numbers standing in for
BP1-BP5's own real already-computed figures, built to match platform_source_data's
real documented shape field-for-field (never guessed). It never touches this
project's real bp6_platform_source_data.json or any real trained model/data, per
this project's standing execution-boundary rule. A PASS here means "BP6's own
reporting code is wired correctly against this shape", not "the real platform
figures are correct" -- that claim is already covered by BP1-BP5's own real,
already-confirmed Notebook 3 validation reports.

This file also closes a real, previously-missing test case: unlike every other
BP's tests/ folder, tests/bp6_enterprise_compliance_monitoring/ had no test file
at all before this hardening pass. It doubles as a permanent regression test for
the 2026-10-02 "repeated Phase/Category label" fix (data-sort attribute +
collapseRepeatedCell) -- the synthetic fixture below deliberately gives BP1/BP2
the same phase and BP3/BP4 the same phase (mirroring the real platform's actual
phase grouping), so a future change that reintroduces the repeated-label bug
would fail test_dashboard_dedup_code_present_and_fixture_has_real_duplicates.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest


def _locate_project_root() -> Path:
    cur = Path.cwd()
    for _ in range(8):
        if (cur / "PROJECT_STRUCTURE_LOCKED.md").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    known = Path.home() / "mnt" / "Documents" / "IBM_AML_RiskIQ_Enterprise_Suite"
    if (known / "PROJECT_STRUCTURE_LOCKED.md").exists():
        return known
    raise FileNotFoundError("Could not locate the project root for BP6 report_builder tests.")


PROJECT_ROOT = _locate_project_root()
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "aml_riskiq" / "reporting"))

import report_builder as rb  # noqa: E402


def _bp_financial(**kw):
    return kw


def _variant(**kw):
    return kw


@pytest.fixture()
def synthetic_platform_source_data():
    """Small, clearly-synthetic platform_source_data matching the real documented
    shape of bp6_platform_source_data.json field-for-field. BP1/BP2 share
    'Phase 1 -- Synthetic Foundation' and BP3/BP4 share 'Phase 2 -- Synthetic
    Network', mirroring the real platform's actual phase grouping, so the
    Phase-column dedup fix has a real duplicate to collapse in this fixture too."""
    shap = [{"name": "Payment Format"}, {"name": "log_amount_received"}]
    reg_map = [f"Synthetic Citation {i} -- BP-wide" for i in range(5)]

    return {
        "generated_at_utc": "2026-01-01T00:00:00+00:00",
        "sourcing_method": "synthetic-test-fixture",
        "bps": {
            "BP1": {
                "name": "Transaction Monitoring & Suspicious Activity Detection",
                "phase": "Phase 1 -- Synthetic Foundation",
                "primary_variant": "LI-Medium",
                "regulatory_mapping": reg_map,
                "top_shap_features": shap,
                "financial": _bp_financial(
                    fewer_fp_alerts=1000,
                    investigator_hours_saved=250,
                    fp_dollar_savings=100_000,
                    additional_real_cases_caught=10,
                    tp_dollar_illustrative=200_000,
                ),
                "variants": {
                    "LI-Medium": _variant(
                        champion="XGBoost",
                        verdict="PASS",
                        n_features=19,
                        threshold=0.5,
                        test_metrics={"precision": 0.30, "recall": 0.40, "pr_auc": 0.12},
                    )
                },
            },
            "BP2": {
                "name": "Typology & Red-Flag Pattern Detection",
                "phase": "Phase 1 -- Synthetic Foundation",
                "primary_variant": "LI-Medium",
                "regulatory_mapping": reg_map,
                "top_shap_features": shap,
                "financial": _bp_financial(
                    more_cases_auto_typed=50,
                    auto_typing_hours_saved=12.5,
                    auto_typing_efficiency_savings=5_000,
                    cases_old_rule_missed=7,
                    typology_confirmation_value=15_000,
                ),
                "variants": {
                    "LI-Medium": _variant(
                        champion="RandomForest",
                        verdict="PASS",
                        n_features=24,
                        test_metrics={"macro_f1": 0.55},
                        class_counts={"fan_out": 500, "cycle": 40},
                    )
                },
            },
            "BP3": {
                "name": "Transaction Network & Graph Intelligence",
                "phase": "Phase 2 -- Synthetic Network",
                "primary_variant": "LI-Medium",
                "regulatory_mapping": reg_map,
                "top_shap_features": [],
                "financial": _bp_financial(
                    n_nodes=20_000,
                    n_edges=40_000,
                    base_rate_pct=0.05,
                    ci95_low=1.5,
                    ci95_high=2.5,
                    ego_network_sizes=[120, 340],
                    no_dollar_reason="no sourced per-account cost basis exists (synthetic fixture)",
                ),
                "variants": {
                    "LI-Medium": _variant(
                        champion="2-hop proximity to a TRAIN-flagged account",
                        verdict="PASS",
                        test_metrics={"lift_ratio": 2.0},
                    )
                },
            },
            "BP4": {
                "name": "Structuring & Smurfing Detection",
                "phase": "Phase 2 -- Synthetic Network",
                "primary_variant": "LI-Medium",
                "regulatory_mapping": reg_map,
                "top_shap_features": shap,
                "named_engineered_features": ["structuring_window_amount_sum"],
                "financial": _bp_financial(
                    fewer_fp_alerts=800,
                    investigator_hours_saved=180,
                    fp_dollar_savings=80_000,
                    additional_real_cases_caught=8,
                    tp_dollar_illustrative=150_000,
                ),
                "variants": {
                    "LI-Medium": _variant(
                        champion="XGBoost",
                        verdict="PASS",
                        n_features=24,
                        threshold=0.6,
                        test_metrics={"precision": 0.20, "recall": 0.50, "pr_auc": 0.10},
                    )
                },
            },
            "BP5": {
                "name": "Correspondent Banking & Cross-Border Wire Risk",
                "phase": "Phase 3 -- Synthetic Cross-Border",
                "primary_variant": "LI-Medium",
                "regulatory_mapping": reg_map,
                "top_shap_features": shap,
                "named_engineered_features": ["sender_country_empirical_risk"],
                "financial": _bp_financial(
                    fewer_fp_alerts=1200,
                    investigator_hours_saved=300,
                    fp_dollar_savings=120_000,
                    additional_real_cases_caught=12,
                    tp_dollar_illustrative=180_000,
                ),
                "variants": {
                    "LI-Medium": _variant(
                        champion="XGBoost",
                        verdict="PASS",
                        n_features=27,
                        threshold=0.55,
                        test_metrics={"precision": 0.25, "recall": 0.35, "pr_auc": 0.11},
                    )
                },
            },
        },
        "platform_rollup": {
            "benefit_category_1_fp_reduction_savings": {
                "bp1": 100_000,
                "bp4": 80_000,
                "bp5": 120_000,
                "total_usd": 300_000,
                "total_investigator_hours_saved": 730,
                "total_fewer_fp_alerts": 3000,
            },
            "benefit_category_2_tp_uplift_value": {
                "bp1": 200_000,
                "bp4": 150_000,
                "bp5": 180_000,
                "total_usd": 530_000,
                "total_additional_cases_caught": 30,
            },
            "benefit_category_3_bp2_typology_lines": {
                "auto_typing_efficiency_savings_usd": 5_000,
                "typology_confirmation_value_usd": 15_000,
            },
            "cost_context": {
                "description": "Synthetic fixture -- no dollar figure, same as the real platform."
            },
            "portfolio_scale": {"bp3_n_nodes": 20_000, "bp3_n_edges": 40_000},
            "headline_grand_total_note": (
                "Synthetic fixture -- BENEFIT categories 1/2/3, COST CONTEXT, and "
                "PORTFOLIO SCALE are never summed into one blended total."
            ),
            "all_bps_verdict_summary": {bp: "PASS" for bp in ("BP1", "BP2", "BP3", "BP4", "BP5")},
        },
    }


def test_compute_platform_status_all_pass(synthetic_platform_source_data):
    status = rb.compute_platform_status(synthetic_platform_source_data)
    assert status["css_class"] == "good"
    assert "RECOMMENDED FOR PRODUCTION" in status["label"]


def test_compute_platform_status_one_failing(synthetic_platform_source_data):
    synthetic_platform_source_data["platform_rollup"]["all_bps_verdict_summary"]["BP2"] = "FAIL"
    status = rb.compute_platform_status(synthetic_platform_source_data)
    assert status["css_class"] == "critical"
    assert "BP2" in status["label"]
    assert "NOT RECOMMENDED" in status["label"]


def test_build_platform_benefit_table_shape(synthetic_platform_source_data):
    roll = synthetic_platform_source_data["platform_rollup"]
    table = rb.build_platform_benefit_table(roll)
    assert len(table) == 13  # 4 (cat1) + 4 (cat2) + 2 (cat3) + 1 (cost) + 2 (scale)
    categories = set(table["Category"])
    assert any("BENEFIT 1" in c for c in categories)
    assert any("BENEFIT 2" in c for c in categories)
    assert any("BENEFIT 3" in c for c in categories)
    assert any("COST CONTEXT" in c for c in categories)
    assert any("PORTFOLIO SCALE" in c for c in categories)


def test_generate_platform_smart_recommendations_bp_tagged(synthetic_platform_source_data):
    recs = rb.generate_platform_smart_recommendations(synthetic_platform_source_data)
    assert len(recs) >= 9
    bp_tags = {r["bp"] for r in recs}
    # every per-BP recommendation (BP1/BP2/BP4/BP5 always; BP3 at least once) plus
    # at least one platform-wide ("") recommendation must be present.
    assert "" in bp_tags
    for bp in ("BP1", "BP2", "BP3", "BP4", "BP5"):
        assert bp in bp_tags
    for r in recs:
        for key in ("title", "specific", "measurable", "achievable", "relevant", "time_bound"):
            assert r.get(key), f"recommendation missing/empty '{key}': {r.get('title')}"


def test_build_bp_business_narratives_platform_all_five(synthetic_platform_source_data):
    narratives = rb.build_bp_business_narratives_platform(synthetic_platform_source_data)
    assert set(narratives.keys()) == {"BP1", "BP2", "BP3", "BP4", "BP5"}
    for bp_id, n in narratives.items():
        for key in (
            "title",
            "verdict",
            "what_it_does",
            "real_performance",
            "production_meaning",
            "methodology",
            "regulatory_citations",
            "business_objective_tightened",
        ):
            assert key in n, f"{bp_id} narrative missing '{key}'"
        assert n["verdict"] == "PASS"


def test_dashboard_dedup_code_present_and_fixture_has_real_duplicates(
    tmp_path, synthetic_platform_source_data
):
    """Regression test for the 2026-10-02 'Phase 1 / Phase 2 repeated on every row'
    fix. Confirms (a) this fixture genuinely has adjacent-row duplicate Phase values
    (BP1/BP2 both 'Phase 1 -- Synthetic Foundation'; BP3/BP4 both 'Phase 2 --
    Synthetic Network'), matching the real platform's own phase grouping, and
    (b) the generated dashboard's JS is syntactically valid and still carries the
    data-sort/collapseRepeatedCell/COLLAPSE_CONFIG fix -- never written to this
    project's real reports/ folder, only to tmp_path."""
    bps = synthetic_platform_source_data["bps"]
    phases = [bps[b]["phase"] for b in ("BP1", "BP2", "BP3", "BP4")]
    assert phases[0] == phases[1], "fixture must have a real adjacent-row Phase duplicate (BP1/BP2)"
    assert phases[2] == phases[3], "fixture must have a real adjacent-row Phase duplicate (BP3/BP4)"

    roll = synthetic_platform_source_data["platform_rollup"]
    context = {
        "bp_id": "BP6",
        "bp_name": "Enterprise AML Compliance Monitoring & Regulatory Reporting (test fixture)",
        "generated_at_utc": "2026-01-01T00:00:00+00:00",
        "platform_source_data": synthetic_platform_source_data,
        "platform_validation_report": {
            "overall_verdict": "PASS",
            "generated_at_utc": "2026-01-01T00:00:00+00:00",
        },
        "phase_rollup": None,
        "benefit_table": rb.build_platform_benefit_table(roll),
        "business_objective": "Synthetic test fixture -- not a deliverable.",
        "business_benefits": ["Synthetic test fixture -- not a deliverable."],
        "regulatory_frameworks": [("Synthetic test fixture", "n/a")],
        "fairness_note": "Synthetic test fixture -- not a deliverable.",
        "caveats": ["Synthetic test fixture -- not a deliverable."],
    }

    out_path = tmp_path / "test_dashboard.html"
    chartjs_path = PROJECT_ROOT / "src" / "aml_riskiq" / "reporting" / "vendor" / "chart.umd.js"
    rb.write_platform_html_dashboard(out_path, context, chartjs_path)

    html = out_path.read_text(encoding="utf-8")
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    assert len(scripts) >= 1

    checked_any = False
    for i, script in enumerate(scripts):
        if len(script.strip()) < 50:
            continue
        js_path = tmp_path / f"script_{i}.js"
        js_path.write_text(script, encoding="utf-8")
        result = subprocess.run(["node", "--check", str(js_path)], capture_output=True, text=True)
        assert result.returncode == 0, f"script block {i} failed node --check: {result.stderr}"
        checked_any = True
    assert checked_any, "expected at least one substantial <script> block to check"

    assert "collapseRepeatedCell" in html
    assert "COLLAPSE_CONFIG" in html
    assert 'data-sort="${r.phase}"' in html
    assert 'data-sort="${r.category}"' in html
