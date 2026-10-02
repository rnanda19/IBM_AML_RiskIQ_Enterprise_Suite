#!/usr/bin/env python3
"""
BP6 Platform Source-Data Extractor -- reads ONLY already-computed, already-saved real
output from BP1-BP5 (each BP's own MODEL_CARD.md / RULE_CARD.md narrative text and its own
NB3 validation_report JSON) and writes ONE canonical, real, zero-fabrication platform
source-data JSON that every BP6 notebook then reads from.

This script performs NO modeling, NO scoring, NO recomputation of any financial or
statistical figure -- every number below is parsed verbatim out of a real file that an
earlier, already-verified BP1-5 Notebook 3/4 run already produced. This materializes the
"each BP's own already-computed summary JSON" that the locked master plan's Section 8
describes (no such single JSON previously existed per BP -- the real figures lived only in
each BP's own rendered MODEL_CARD.md/RULE_CARD.md text and its own NB3 validation_report
JSON), so this script is the one-time, deterministic, read-only bridge between those real
artifacts and BP6's own 4-notebook rollup pipeline. Re-run any time after a BP1-5 report
changes -- it always re-parses the current real files, never caches a stale number.

Zero-fabrication discipline: if any expected real file, section, or figure is missing, this
script raises loudly (or records an explicit "NOT YET COMPUTED" marker) rather than
guessing, estimating, or silently defaulting.
"""
import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

try:
    ROOT = Path(__file__).resolve().parent  # when run as a real script (python3 this_file.py)
except NameError:
    ROOT = Path.cwd()  # when pasted/run directly in a notebook cell -- __file__ does not exist there
REPORTS = Path("reports")

USD = r"\$([\d,]+)"


def _usd_to_int(s: str) -> int:
    return int(s.replace(",", ""))


def _read(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Required real source file missing: {path}")
    return path.read_text(encoding="utf-8")


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Required real validation report missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def parse_binary_model_card(bp_id: str, folder: str) -> dict:
    """BP1 / BP4 / BP5 -- binary classification MODEL_CARD.md real Financial Impact Summary."""
    text = _read(REPORTS / folder / "MODEL_CARD.md")

    fi_section_match = re.search(
        r"## Financial Impact Summary\n(.*?)\n##", text, re.S)
    if not fi_section_match:
        raise ValueError(f"{bp_id}: Financial Impact Summary section not found in MODEL_CARD.md")
    fi_text = fi_section_match.group(1)

    fp_line = re.search(
        r"False-positive-reduction savings \(ASSUMPTION\): " + USD +
        r" \(\$[\d.]+[MK]?\) \(([\d,]+) investigator hours, ([\d,]+) fewer false-positive alerts\)",
        fi_text)
    tp_line = re.search(
        r"True-positive-uplift illustrative regulatory-exposure-avoidance \(ASSUMPTION\): " + USD +
        r" \(\$[\d.]+[MK]?\) \(\+?([\d,]+) additional real cases caught\)",
        fi_text)
    if not fp_line or not tp_line:
        raise ValueError(f"{bp_id}: could not parse real dollar figures out of Financial Impact Summary -- "
                          f"regex may be stale against the real file's current wording.\n{fi_text}")

    return {
        "bp_id": bp_id,
        "fp_dollar_savings": _usd_to_int(fp_line.group(1)),
        "investigator_hours_saved": int(fp_line.group(2).replace(",", "")),
        "fewer_fp_alerts": int(fp_line.group(3).replace(",", "")),
        "tp_dollar_illustrative": _usd_to_int(tp_line.group(1)),
        "additional_real_cases_caught": int(tp_line.group(2).replace(",", "")),
    }


def parse_bp2_model_card(bp_id: str, folder: str) -> dict:
    """BP2 -- multiclass typology MODEL_CARD.md real Financial Impact Summary (different
    wording from the binary-path BPs -- auto-typing efficiency + typology-confirmation value)."""
    text = _read(REPORTS / folder / "MODEL_CARD.md")
    fi_section_match = re.search(r"## Financial Impact Summary\n(.*?)\n##", text, re.S)
    if not fi_section_match:
        raise ValueError(f"{bp_id}: Financial Impact Summary section not found in MODEL_CARD.md")
    fi_text = fi_section_match.group(1)

    eff_line = re.search(
        r"Auto-typing efficiency savings \(ASSUMPTION\): " + USD +
        r" \(([\d.]+) investigator hours, \+?([\d,]+) more cases correctly auto-typed\)",
        fi_text)
    conf_line = re.search(
        r"Illustrative typology-confirmation value \(ASSUMPTION\): " + USD +
        r" \(\$[\d.]+[MK]?\) \(([\d,]+) real cases the old single-guess rule structurally could not identify\)",
        fi_text)
    if not eff_line or not conf_line:
        raise ValueError(f"{bp_id}: could not parse real dollar figures out of Financial Impact Summary.\n{fi_text}")

    return {
        "bp_id": bp_id,
        "auto_typing_efficiency_savings": _usd_to_int(eff_line.group(1)),
        "auto_typing_hours_saved": float(eff_line.group(2)),
        "more_cases_auto_typed": int(eff_line.group(3).replace(",", "")),
        "typology_confirmation_value": _usd_to_int(conf_line.group(1)),
        "cases_old_rule_missed": int(conf_line.group(2).replace(",", "")),
    }


def parse_bp3_rule_card(bp_id: str, folder: str) -> dict:
    """BP3 -- structural RULE_CARD.md: no dollar figure exists (disclosed honestly in the
    real file itself) -- only real volume-scale and network-lift figures."""
    text = _read(REPORTS / folder / "RULE_CARD.md")

    nodes_edges = re.search(
        r"([\d,]+) real distinct \(Bank, Account\) nodes, ([\d,]+) real distinct directed edges",
        text)
    lift = re.search(r"Real network-lift ratio \(point estimate\): ([\d.]+)x", text)
    ci = re.search(r"Real bootstrap 95% CI: \[([\d.]+)x, ([\d.]+)x\]", text)
    ego = re.search(
        r"real network sizes of ([\d,]+), ([\d,]+), ([\d,]+) accounts", text)
    base_rate = re.search(r"real base rate of ([\d.]+)%", text)
    verdict = re.search(r"Overall Verdict \|\n\| LI-Medium \| .*? \| .*? \| .*? \| .*? \| (\w+) \| (\w+) \| (\w+) \|", text)

    if not (nodes_edges and lift and ci and ego and base_rate):
        raise ValueError(f"{bp_id}: could not parse one or more real figures out of RULE_CARD.md")

    return {
        "bp_id": bp_id,
        "has_dollar_figure": False,
        "no_dollar_reason": "No sourced real per-account investigation-cost basis exists for this BP "
                             "(disclosed honestly in the real RULE_CARD.md -- none is invented here).",
        "n_nodes": int(nodes_edges.group(1).replace(",", "")),
        "n_edges": int(nodes_edges.group(2).replace(",", "")),
        "network_lift_ratio": float(lift.group(1)),
        "ci95_low": float(ci.group(1)),
        "ci95_high": float(ci.group(2)),
        "base_rate_pct": float(base_rate.group(1)),
        "ego_network_sizes": [int(x.replace(",", "")) for x in ego.groups()],
    }


def load_validation_report(bp_folder: str, variant_file: str) -> dict:
    return _load_json(REPORTS / bp_folder / variant_file)


def parse_business_objective_and_regulatory(bp_id: str, folder: str, card_filename: str) -> dict:
    """Pure text extraction (no recomputation) of each BP's own real `## Business Objective`
    and `## Regulatory Mapping` sections, straight out of its own MODEL_CARD.md / RULE_CARD.md
    (BP3's RULE_CARD.md uses the identical `## Business Objective` heading). Also pulls the
    real named-engineered-feature list out of BP4/BP5's own Business Objective sentence
    (parsed from the real text, never hardcoded, so this stays correct if that text changes).
    Raises loudly if a required section is missing -- never guesses."""
    text = _read(REPORTS / folder / card_filename)

    bo_match = re.search(r"## Business Objective\n(.*?)\n##", text, re.S)
    if not bo_match:
        raise ValueError(f"{bp_id}: '## Business Objective' section not found in {card_filename}")
    business_objective = bo_match.group(1).strip()

    rm_match = re.search(r"## Regulatory Mapping\n(.*?)\n##", text, re.S)
    if not rm_match:
        raise ValueError(f"{bp_id}: '## Regulatory Mapping' section not found in {card_filename}")
    regulatory_mapping = [
        line.strip().lstrip("- ").strip()
        for line in rm_match.group(1).split("\n")
        if line.strip().startswith("-")
    ]
    if not regulatory_mapping:
        raise ValueError(f"{bp_id}: '## Regulatory Mapping' section parsed but yielded no real bullet lines")

    result = {
        "business_objective": business_objective,
        "regulatory_mapping": regulatory_mapping,
    }

    # Real named-engineered-feature list -- only BP4/BP5's Business Objective text contains this
    # sentence pattern ("-- <comma-separated real feature names> --"); BP1/BP2/BP3 have no
    # analogous sentence and correctly get no key here (never fabricated).
    named_feat_match = re.search(r"-- ([a-z_]+(?:, [a-z_]+)+) --", business_objective)
    if named_feat_match:
        result["named_engineered_features"] = named_feat_match.group(1).split(", ")

    return result


def top5_shap_features(validation_report: dict, bp_id: str) -> list:
    """Real top-5 entries of the already-computed `shap_mean_abs_importance` dict from a BP's
    own real NB3 validation_report JSON (BP1/BP2/BP4/BP5 all carry this key; BP3 has no trained
    model and correctly has none -- callers must not call this for BP3)."""
    shap = validation_report.get("shap_mean_abs_importance")
    if not isinstance(shap, dict) or not shap:
        raise ValueError(f"{bp_id}: 'shap_mean_abs_importance' missing or empty in its real validation_report JSON")
    ranked = sorted(shap.items(), key=lambda kv: -kv[1])[:5]
    return [{"name": name, "value": value} for name, value in ranked]


def main() -> None:
    out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "sourcing_method": (
            "Every figure below was parsed verbatim from a real, already-generated "
            "BP1-BP5 report file (MODEL_CARD.md / RULE_CARD.md Financial Impact / Rule "
            "Details section, and each BP's own real NB3 validation_report JSON). "
            "No figure here is recomputed, estimated, or fabricated -- this script performs "
            "pure extraction of already-computed real output, per the locked master plan's "
            "Section 8 'recomputing nothing' rule and Section 7A's 'Pure sum of BP1-BP5's "
            "own already-computed deltas' rule for BP6."
        ),
        "bps": {},
    }

    # ---- BP1 ----
    bp1_fin = parse_binary_model_card("BP1", "bp1_transaction_monitoring_detection")
    bp1_hi = load_validation_report("bp1_transaction_monitoring_detection",
                                     "bp1_notebook3_validation_report_hi_small.json")
    bp1_li = load_validation_report("bp1_transaction_monitoring_detection",
                                     "bp1_notebook3_validation_report_li_medium.json")
    bp1_card = parse_business_objective_and_regulatory(
        "BP1", "bp1_transaction_monitoring_detection", "MODEL_CARD.md")
    out["bps"]["BP1"] = {
        "name": "Transaction Monitoring & Suspicious Activity Detection",
        "phase": "Phase 1 -- Detection Foundation",
        "category": "binary",
        "financial": bp1_fin,
        "primary_variant": "LI-Medium",
        "business_objective": bp1_card["business_objective"],
        "regulatory_mapping": bp1_card["regulatory_mapping"],
        "top_shap_features": top5_shap_features(bp1_li, "BP1"),
        "variants": {
            "HI-Small": {"champion": bp1_hi["champion_name"], "threshold": bp1_hi["selected_threshold"],
                          "test_metrics": bp1_hi["test_metrics"], "verdict": bp1_hi["overall_verdict"],
                          "n_features": len(bp1_hi["feature_cols"])},
            "LI-Medium": {"champion": bp1_li["champion_name"], "threshold": bp1_li["selected_threshold"],
                          "test_metrics": bp1_li["test_metrics"], "verdict": bp1_li["overall_verdict"],
                          "n_features": len(bp1_li["feature_cols"])},
        },
    }

    # ---- BP2 ----
    bp2_fin = parse_bp2_model_card("BP2", "bp2_typology_redflag_detection")
    bp2_li = load_validation_report("bp2_typology_redflag_detection",
                                     "bp2_notebook3_validation_report_li_medium.json")
    bp2_card = parse_business_objective_and_regulatory(
        "BP2", "bp2_typology_redflag_detection", "MODEL_CARD.md")
    out["bps"]["BP2"] = {
        "name": "Typology & Red-Flag Pattern Detection",
        "phase": "Phase 1 -- Detection Foundation",
        "category": "multiclass",
        "financial": bp2_fin,
        "primary_variant": "LI-Medium",
        "business_objective": bp2_card["business_objective"],
        "regulatory_mapping": bp2_card["regulatory_mapping"],
        "top_shap_features": top5_shap_features(bp2_li, "BP2"),
        "variants": {
            "LI-Medium": {"champion": bp2_li["champion_name"], "test_metrics": bp2_li["test_metrics"],
                          "verdict": bp2_li["overall_verdict"], "n_features": len(bp2_li["feature_cols"]),
                          "class_counts": bp2_li["class_counts"]},
        },
    }

    # ---- BP3 ----
    bp3_fin = parse_bp3_rule_card("BP3", "bp3_network_graph_intelligence")
    bp3_li = load_validation_report("bp3_network_graph_intelligence",
                                     "bp3_notebook3_validation_report_li_medium.json")
    bp3_card = parse_business_objective_and_regulatory(
        "BP3", "bp3_network_graph_intelligence", "RULE_CARD.md")
    out["bps"]["BP3"] = {
        "name": "Transaction Network & Graph Intelligence",
        "phase": "Phase 2 -- Network & Specialized Typology",
        "category": "structural_rule",
        "financial": bp3_fin,
        "primary_variant": "LI-Medium",
        "business_objective": bp3_card["business_objective"],
        "regulatory_mapping": bp3_card["regulatory_mapping"],
        # No "top_shap_features" key for BP3 -- genuinely N/A (no trained model), never a
        # substitute invented; disclosed honestly rather than silently absent.
        "variants": {
            "LI-Medium": {"champion": bp3_li["champion_name"], "test_metrics": bp3_li["test_metrics"],
                          "verdict": bp3_li["overall_verdict"]},
        },
    }

    # ---- BP4 ----
    bp4_fin = parse_binary_model_card("BP4", "bp4_structuring_smurfing_detection")
    bp4_hi = load_validation_report("bp4_structuring_smurfing_detection",
                                     "bp4_notebook3_validation_report_hi_small.json")
    bp4_li = load_validation_report("bp4_structuring_smurfing_detection",
                                     "bp4_notebook3_validation_report_li_medium.json")
    bp4_card = parse_business_objective_and_regulatory(
        "BP4", "bp4_structuring_smurfing_detection", "MODEL_CARD.md")
    if "named_engineered_features" not in bp4_card:
        raise ValueError("BP4: expected a real named-engineered-feature list in its Business "
                          "Objective text but none was found -- regex may be stale.")
    out["bps"]["BP4"] = {
        "name": "Structuring & Smurfing Detection",
        "phase": "Phase 2 -- Network & Specialized Typology",
        "category": "binary",
        "financial": bp4_fin,
        "primary_variant": "LI-Medium",
        "business_objective": bp4_card["business_objective"],
        "regulatory_mapping": bp4_card["regulatory_mapping"],
        "named_engineered_features": bp4_card["named_engineered_features"],
        "top_shap_features": top5_shap_features(bp4_li, "BP4"),
        "variants": {
            "HI-Small": {"champion": bp4_hi["champion_name"], "threshold": bp4_hi["selected_threshold"],
                          "test_metrics": bp4_hi["test_metrics"], "verdict": bp4_hi["overall_verdict"],
                          "n_features": len(bp4_hi["feature_cols"])},
            "LI-Medium": {"champion": bp4_li["champion_name"], "threshold": bp4_li["selected_threshold"],
                          "test_metrics": bp4_li["test_metrics"], "verdict": bp4_li["overall_verdict"],
                          "n_features": len(bp4_li["feature_cols"])},
        },
    }

    # ---- BP5 ----
    bp5_fin = parse_binary_model_card("BP5", "bp5_correspondent_banking_crossborder_risk")
    bp5_hi = load_validation_report("bp5_correspondent_banking_crossborder_risk",
                                     "bp5_notebook3_validation_report_hi_small.json")
    bp5_li = load_validation_report("bp5_correspondent_banking_crossborder_risk",
                                     "bp5_notebook3_validation_report_li_medium.json")
    bp5_card = parse_business_objective_and_regulatory(
        "BP5", "bp5_correspondent_banking_crossborder_risk", "MODEL_CARD.md")
    if "named_engineered_features" not in bp5_card:
        raise ValueError("BP5: expected a real named-engineered-feature list in its Business "
                          "Objective text but none was found -- regex may be stale.")
    out["bps"]["BP5"] = {
        "name": "Correspondent Banking & Cross-Border Wire Risk",
        "phase": "Phase 3 -- Cross-Border Intelligence",
        "category": "binary",
        "financial": bp5_fin,
        "primary_variant": "LI-Medium",
        "business_objective": bp5_card["business_objective"],
        "regulatory_mapping": bp5_card["regulatory_mapping"],
        "named_engineered_features": bp5_card["named_engineered_features"],
        "top_shap_features": top5_shap_features(bp5_li, "BP5"),
        "variants": {
            "HI-Small": {"champion": bp5_hi["champion_name"], "threshold": bp5_hi["selected_threshold"],
                          "test_metrics": bp5_hi["test_metrics"], "verdict": bp5_hi["overall_verdict"],
                          "n_features": len(bp5_hi["feature_cols"])},
            "LI-Medium": {"champion": bp5_li["champion_name"], "threshold": bp5_li["selected_threshold"],
                          "test_metrics": bp5_li["test_metrics"], "verdict": bp5_li["overall_verdict"],
                          "n_features": len(bp5_li["feature_cols"])},
        },
    }

    # ---- Platform-level pure sums (BENEFIT category only -- never blended with each other) ----
    binary_bps = ["BP1", "BP4", "BP5"]
    fp_total = sum(out["bps"][b]["financial"]["fp_dollar_savings"] for b in binary_bps)
    tp_total = sum(out["bps"][b]["financial"]["tp_dollar_illustrative"] for b in binary_bps)
    hours_total = sum(out["bps"][b]["financial"]["investigator_hours_saved"] for b in binary_bps)
    fp_alerts_total = sum(out["bps"][b]["financial"]["fewer_fp_alerts"] for b in binary_bps)
    cases_total = sum(out["bps"][b]["financial"]["additional_real_cases_caught"] for b in binary_bps)

    bp2_eff = out["bps"]["BP2"]["financial"]["auto_typing_efficiency_savings"]
    bp2_conf = out["bps"]["BP2"]["financial"]["typology_confirmation_value"]

    out["platform_rollup"] = {
        "benefit_category_1_fp_reduction_savings": {
            "description": "Pure sum of BP1+BP4+BP5's own already-computed false-positive-reduction "
                            "$ savings (ASSUMPTION-labeled). BP2's analogous auto-typing efficiency "
                            "savings is kept as its own separate line (different unit basis -- "
                            "investigator-hours-per-alert vs. auto-typing-hours -- never blended "
                            "into this sum, per the locked never-blend-categories rule).",
            "bp1": out["bps"]["BP1"]["financial"]["fp_dollar_savings"],
            "bp4": out["bps"]["BP4"]["financial"]["fp_dollar_savings"],
            "bp5": out["bps"]["BP5"]["financial"]["fp_dollar_savings"],
            "total_usd": fp_total,
            "total_investigator_hours_saved": hours_total,
            "total_fewer_fp_alerts": fp_alerts_total,
        },
        "benefit_category_2_tp_uplift_value": {
            "description": "Pure sum of BP1+BP4+BP5's own already-computed true-positive-uplift "
                            "illustrative regulatory-exposure-avoidance $ (ASSUMPTION-labeled). BP2's "
                            "analogous typology-confirmation value is kept separate (different real "
                            "case subset and ASSUMPTION basis -- never blended, per the locked rule).",
            "bp1": out["bps"]["BP1"]["financial"]["tp_dollar_illustrative"],
            "bp4": out["bps"]["BP4"]["financial"]["tp_dollar_illustrative"],
            "bp5": out["bps"]["BP5"]["financial"]["tp_dollar_illustrative"],
            "total_usd": tp_total,
            "total_additional_cases_caught": cases_total,
        },
        "benefit_category_3_bp2_typology_lines": {
            "description": "BP2's two real figures, kept on their own two lines -- never summed into "
                            "categories 1 or 2 above (different ASSUMPTION bases and case subsets).",
            "auto_typing_efficiency_savings_usd": bp2_eff,
            "typology_confirmation_value_usd": bp2_conf,
        },
        "cost_context": {
            "description": "Informational only, never summed into any headline figure (locked "
                            "Section 8 rule). This platform has no real sourced build/operating-cost "
                            "figure for any BP -- none is invented here; this section intentionally "
                            "carries no dollar figure, consistent with this platform's zero-fabrication "
                            "discipline.",
        },
        "portfolio_scale": {
            "description": "Volume context only, never dollarized or summed into the headline "
                            "(locked Section 8 rule). BP3's real network-coverage volume is structurally "
                            "distinct from BP1/2/4/5's transaction-level populations and is shown on its "
                            "own line, never combined with them.",
            "bp3_n_nodes": out["bps"]["BP3"]["financial"]["n_nodes"],
            "bp3_n_edges": out["bps"]["BP3"]["financial"]["n_edges"],
        },
        "headline_grand_total_note": (
            "This platform reports THREE separate BENEFIT lines (categories 1, 2, and 3 above) -- "
            "never one blended grand total -- per the locked Section 7A/Section 8 "
            "never-summed-across-categories discipline. A reader wanting a single number must choose "
            "which category answers their question; none is privileged as 'the' headline by this report."
        ),
        "all_bps_verdict_summary": {
            bp: out["bps"][bp]["variants"][out["bps"][bp]["primary_variant"]]["verdict"]
            for bp in ["BP1", "BP2", "BP3", "BP4", "BP5"]
        },
    }

    dest_dir = REPORTS / "bp6_enterprise_compliance_monitoring"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "bp6_platform_source_data.json"
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"WROTE: {dest} ({dest.stat().st_size:,} bytes)")
    print(json.dumps(out["platform_rollup"], indent=2))


if __name__ == "__main__":
    main()
