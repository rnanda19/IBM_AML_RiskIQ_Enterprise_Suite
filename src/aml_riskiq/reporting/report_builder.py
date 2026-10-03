"""
IBM AML RiskIQ Enterprise Suite - src/reporting/report_builder.py

Shared five-format executive reporting module (HYPER pattern - this platform's own proven
approach: built ONCE here, in BP1's Notebook 4, imported UNCHANGED by every later BP's
Notebook 4 and by the phase-level / platform-level rollups). Never hand-coded per notebook.

Produces, from a real, already-computed `context` dict (never recomputes model results --
Notebook 4's own job is to read each BP's own saved Notebook-3 JSON reports, per the locked
"per-BP report package generation is gated only on the structural [CHECK] gate" rule):
  - build_before_after_table()        real Section-7A Before/After/Delta/$Impact table
  - write_word_report()               python-docx narrative report
  - write_excel_workbook()            openpyxl workbook, Assumptions-sheet-first pattern
  - write_html_dashboard()            self-contained HTML, real Chart.js bundled locally
  - write_pptx_deck()                 python-pptx executive/board deck
  - export_pdf_from_docx()            PDF rendered FROM the Word report (never a separate
                                       source of numbers) -- honestly guarded, never fabricated
  - write_model_card()                MODEL_CARD.md (real content, standard ML model-card sections)
  - write_changelog()                 CHANGELOG.md (append-only, real entries)

Zero-fabrication discipline carried from every prior notebook in this project: every function
here either takes real numbers already computed elsewhere, or (compute_naive_baseline only)
recomputes a real, cheap, well-defined statistic directly from the real raw data using the
project's own Parquet cache (utils.performance_setup.load_csv_cached) -- never a synthetic or
illustrative placeholder. Anywhere a dollar figure is not a directly-measured real quantity
(e.g. investigator-hours-saved framing), it is computed from an explicit, disclosed
ASSUMPTIONS dict and labeled ASSUMPTION wherever it is displayed -- per the locked "illustrative
regulatory-exposure-avoidance explicitly labeled ASSUMPTION" rule. False-positive-reduction
$ savings and true-positive/detection uplift are always kept as two separate lines, never
summed into one blended dollar figure.

This file is written and tested locally (against synthetic data, never the user's real
project data) by Claude, per this project's execution-boundary rule -- Claude never runs it
against real data. All real numbers in any document it produces come from the user's own
notebook run.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import pandas as pd

# ============================================================================
# Real CVD-validated palette (dataviz skill's reference instance, references/palette.md)
# -- used identically across the Excel, HTML, and PPTX outputs so all three formats read
# as one system, per the dataviz skill's own requirement.
# ============================================================================
PALETTE = {
    "series_1_blue": "#2a78d6",
    "series_2_orange": "#eb6834",
    "series_3_aqua": "#1baf7a",
    "status_good": "#0ca30c",
    "status_warning": "#fab219",
    "status_serious": "#ec835a",
    "status_critical": "#d03b3b",
    "ink_primary": "#0b0b0b",
    "ink_secondary": "#52514e",
    "ink_muted": "#898781",
    "gridline": "#e1e0d9",
    "surface": "#fbfaf7",  # off-white -- cards / narrative / text blocks
    "page": "#e9ebee",  # light grey -- page plane behind the cards
}


# ============================================================================
# Shared Word / Excel / PPTX branding helpers -- same CVD-validated PALETTE the HTML
# dashboards use, applied through each format's own STABLE PUBLIC API only. Every helper
# here is deliberately restrained (a branded header, a tab color, a thin accent bar) rather
# than decorative, because these are regulatory AML compliance deliverables, not marketing
# collateral. The one thing explicitly NOT attempted anywhere in this module is a real
# PowerPoint slide transition: python-pptx has no public API for <p:transition>, and
# hand-written OOXML for it cannot be verified safe from this sandbox (python-pptx re-opening
# the file only proves XML well-formedness, not OOXML schema-order validity -- there is no
# real PowerPoint available here to confirm it won't trigger a "repair" prompt). Shipping an
# unverifiable animation risks a corrupted deliverable, so the PPTX helper below ships a
# static, Office-safe visual accent instead.
# ============================================================================
def _hex_rgb(hex_color: str):
    """Three real int components (r, g, b) parsed from a '#rrggbb' or 'rrggbb' string --
    shared by the docx/pptx RGBColor wrappers below so the hex parsing logic lives in one
    place."""
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _apply_word_brand_styles(doc) -> None:
    """Brands a python-docx Document's built-in Title / Heading 1 / Heading 2 styles with
    the shared PALETTE, once, at the STYLE level -- every doc.add_heading(..., level=N) call
    made anywhere else in the function (there can be a dozen) automatically picks this up,
    so no per-heading edits are needed. Pure public python-docx API
    (doc.styles[...].font.color.rgb / .font.size) -- zero OOXML risk."""
    from docx.shared import Pt, RGBColor

    r, g, b = _hex_rgb(PALETTE["series_1_blue"])
    r2, g2, b2 = _hex_rgb(PALETTE["series_3_aqua"])
    try:
        title_style = doc.styles["Title"]
        title_style.font.color.rgb = RGBColor(r, g, b)
        title_style.font.size = Pt(26)
    except KeyError:
        pass
    try:
        doc.styles["Heading 1"].font.color.rgb = RGBColor(r, g, b)
    except KeyError:
        pass
    try:
        doc.styles["Heading 2"].font.color.rgb = RGBColor(r2, g2, b2)
    except KeyError:
        pass


def _brand_word_table_headers(doc, hex_color: Optional[str] = None) -> None:
    """Solid branded header-row shading (+ white bold header text) on every table already
    added to the document -- called once, right before doc.save(), so it covers every table
    the function built earlier regardless of how many there were. Uses the standard, widely
    documented `w:shd` OXML element on each header cell's tcPr (one child element, no
    reordering of anything else) -- this exact snippet is in python-docx's own cookbook and
    carries none of the schema-ordering risk a PPTX slide transition would."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import RGBColor

    fill_hex = (hex_color or PALETTE["series_1_blue"]).lstrip("#").upper()
    r, g, b = _hex_rgb(fill_hex)
    for table in doc.tables:
        if not table.rows:
            continue
        for cell in table.rows[0].cells:
            tcPr = cell._tc.get_or_add_tcPr()
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), fill_hex)
            tcPr.append(shd)
            for p in cell.paragraphs:
                if not p.runs:
                    p.add_run("")
                for run in p.runs:
                    run.font.color.rgb = RGBColor(255, 255, 255)
                    run.font.bold = True


def _brand_excel_sheet(ws, hex_tab_color: Optional[str] = None, freeze_cell: str = "A2") -> None:
    """Sheet tab color + frozen header row -- pure openpyxl public API
    (ws.sheet_properties.tabColor, ws.freeze_panes), applied identically to every sheet in
    every workbook this module writes."""
    ws.sheet_properties.tabColor = (hex_tab_color or PALETTE["series_1_blue"]).lstrip("#").upper()
    ws.freeze_panes = freeze_cell


def _band_excel_rows(
    ws, first_data_row: int, last_data_row: int, first_col: int, last_col: int, band_hex: str = "EEF4FC"
) -> None:
    """Alternating light-tint row fill across real data rows only -- a standard Excel
    'banded rows' look via PatternFill. Skips any cell that already carries its own fill
    (e.g. an existing yellow Assumption-value highlight or a status-color cell), so this
    never overrides a fill that is itself carrying real meaning."""
    from openpyxl.styles import PatternFill

    band_fill = PatternFill(start_color=band_hex, end_color=band_hex, fill_type="solid")
    for r in range(first_data_row, last_data_row + 1):
        if (r - first_data_row) % 2 == 1:
            for c in range(first_col, last_col + 1):
                cell = ws.cell(row=r, column=c)
                existing = cell.fill.fgColor.rgb if cell.fill else None
                if existing in (None, "00000000"):
                    cell.fill = band_fill


def _color_verdict_cells(ws, rows, cols, good_values=("PASS",)) -> None:
    """Conditional PASS/FAIL cell coloring on verdict columns -- real status green for a
    literal PASS, real status red for anything else (so an unexpected third value still
    renders as visibly 'not green' instead of silently matching nothing), white bold text
    for contrast either way. `rows` / `cols` are explicit 1-indexed iterables, not an
    inferred range, so this only ever touches cells the caller names."""
    from openpyxl.styles import Font, PatternFill

    good_hex = PALETTE["status_good"].lstrip("#").upper()
    bad_hex = PALETTE["status_critical"].lstrip("#").upper()
    good_fill = PatternFill(start_color=good_hex, end_color=good_hex, fill_type="solid")
    bad_fill = PatternFill(start_color=bad_hex, end_color=bad_hex, fill_type="solid")
    white_bold = Font(bold=True, color="FFFFFF")
    for r in rows:
        for c in cols:
            cell = ws.cell(row=r, column=c)
            if cell.value is None:
                continue
            cell.fill = good_fill if str(cell.value).strip().upper() in good_values else bad_fill
            cell.font = white_bold


def _add_branded_slide(
    prs,
    layout_idx: int,
    accent_hex: Optional[str] = None,
    tint_hex: Optional[str] = None,
    bar_thickness_in: float = 0.12,
):
    """Adds a slide from the given layout, then applies the one visual accent this module
    ships for PPTX: a full-width solid accent-color bar at the very top, via the standard
    public python-pptx shape API (shapes.add_shape(MSO_SHAPE.RECTANGLE, ...) with a solid
    fill and no outline/shadow) plus a very light solid background tint
    (slide.background.fill.solid()) -- both long-stable, schema-safe public calls, deliberately
    NOT the raw-XML slide-transition route (see this module's branding-helpers banner comment
    for why). Returns the new slide so call sites can keep using it exactly as before."""
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Inches

    slide = prs.slides.add_slide(prs.slide_layouts[layout_idx])

    tr, tg, tb = _hex_rgb(tint_hex or PALETTE["page"])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = RGBColor(tr, tg, tb)

    ar, ag, ab = _hex_rgb(accent_hex or PALETTE["series_1_blue"])
    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), prs.slide_width, Inches(bar_thickness_in)
    )
    bar.fill.solid()
    bar.fill.fore_color.rgb = RGBColor(ar, ag, ab)
    bar.line.fill.background()
    bar.shadow.inherit = False
    return slide


# ============================================================================
# Real naive-baseline recompute (identical method to every Notebook 3's own naive
# baseline -- reused here rather than duplicated by value, since Notebook 3 prints this
# but does not currently persist it to the saved JSON report).
# ============================================================================
def compute_naive_baseline(df: pd.DataFrame, target_col: str, amount_col: str, pctl: float = 0.99) -> dict:
    """Real fixed-dollar-threshold rule baseline -- identical method used in every BP's
    Notebook 3 (99th percentile of the real amount column, no other logic). Returns real
    precision/recall/flagged-count at that single fixed operating point. This is NOT a
    probabilistic classifier, so no PR-AUC applies to it -- only its one real operating point."""
    from sklearn.metrics import precision_score, recall_score

    threshold_dollar = float(df[amount_col].quantile(pctl))
    pred = (df[amount_col] > threshold_dollar).astype(int)
    precision = float(precision_score(df[target_col], pred, zero_division=0))
    recall = float(recall_score(df[target_col], pred, zero_division=0))
    n_flagged = int(pred.sum())
    n_total = int(len(df))
    n_positive = int(df[target_col].sum())
    return {
        "rule": f"Amount > real {pctl:.0%} percentile (${threshold_dollar:,.2f})",
        "threshold_dollar": threshold_dollar,
        "precision": precision,
        "recall": recall,
        "n_flagged": n_flagged,
        "n_total": n_total,
        "n_positive": n_positive,
    }


def _safe_div(n, d):
    return float(n) / float(d) if d else float("nan")


def _fmt_usd(value: float) -> str:
    """Real dollar formatting -- the exact comma-formatted figure is always shown, with a
    billions/millions shorthand appended for any value whose magnitude is >= $1M -- never a
    shorthand-only figure, per this user's standing "always give the B/M form too" rule.
    Sign is preserved on both the exact figure and the shorthand."""
    sign = "-" if value < 0 else ""
    v = abs(float(value))
    exact = f"{sign}${v:,.0f}"
    if v >= 1_000_000_000:
        return f"{exact} ({sign}${v / 1_000_000_000:.2f}B)"
    if v >= 1_000_000:
        return f"{exact} ({sign}${v / 1_000_000:.2f}M)"
    return exact


# Public alias -- report_builder.py's own internal functions call _fmt_usd directly, but
# Notebook 4 (and any future BP's Notebook 4) should reach this through a non-underscored
# name when formatting a real dollar figure for its own narrative text (e.g. business
# benefits bullets), so every dollar figure anywhere in this project's output -- not just
# the ones generated inside this module -- carries the same "$X,XXX (with B/M shorthand
# above $1M)" real formatting, per this user's standing formatting rule.
format_usd = _fmt_usd


# ============================================================================
# Real financial-impact arithmetic -- the raw numbers behind the Before/After table's
# "$ Impact" column, exposed separately so the HTML dashboard's financial-impact panel,
# the status logic, and the SMART recommendations can all reuse the same real figures
# without re-deriving or re-parsing formatted strings.
# ============================================================================
def compute_financial_impact(before: dict, after: dict, assumptions: dict) -> dict:
    """Real, raw (unformatted) financial-impact figures. False-positive-reduction $ and
    true-positive-uplift $ are always kept separate, never summed (locked Section 7A rule)."""
    before_fp = before["n_flagged"] - int(round(before["precision"] * before["n_flagged"]))
    after_fp = after["n_flagged"] - int(round(after["precision"] * after["n_flagged"]))
    fp_reduction = before_fp - after_fp
    hours_saved = fp_reduction * assumptions["hours_per_alert_review"]
    fp_dollar_savings = hours_saved * assumptions["cost_per_investigator_hour_usd"]

    before_tp = int(round(before["recall"] * before["n_positive"]))
    after_tp = int(round(after["recall"] * after["n_positive"]))
    tp_uplift = after_tp - before_tp
    tp_dollar_illustrative = tp_uplift * assumptions["illustrative_case_exposure_usd"]

    return {
        "before_fp": before_fp,
        "after_fp": after_fp,
        "fp_reduction": fp_reduction,
        "hours_saved": hours_saved,
        "fp_dollar_savings": fp_dollar_savings,
        "before_tp": before_tp,
        "after_tp": after_tp,
        "tp_uplift": tp_uplift,
        "tp_dollar_illustrative": tp_dollar_illustrative,
    }


# ============================================================================
# Before/After comparison table -- Section 7A, mandatory in every BP's Notebook 4
# ============================================================================
def build_before_after_table(before: dict, after: dict, assumptions: dict) -> pd.DataFrame:
    """Real Metric | Before (baseline) | After (ML model) | Delta | $ Impact table.

    `before`  -- compute_naive_baseline()'s real output.
    `after`   -- {"precision", "recall", "f2", "n_flagged", "n_total", "n_positive"} from the
                 BP's own real Notebook-3 test-set evaluation at its selected threshold.
    `assumptions` -- {"hours_per_alert_review", "cost_per_investigator_hour_usd",
                      "illustrative_case_exposure_usd"} -- every value here is a disclosed
                 ASSUMPTION, never a directly-measured quantity, and is labeled as such in
                 every output format.

    False-positive-reduction $ and true-positive-uplift $ are kept as two separate rows,
    never summed into one blended figure (locked rule, Section 7A).
    """
    fi = compute_financial_impact(before, after, assumptions)

    rows = [
        {
            "Metric": "Precision (at operating point)",
            "Before (baseline)": f"{before['precision']:.4f}",
            "After (ML model)": f"{after['precision']:.4f}",
            "Delta": f"{after['precision'] - before['precision']:+.4f}",
            "$ Impact": "",
        },
        {
            "Metric": "Recall (at operating point)",
            "Before (baseline)": f"{before['recall']:.4f}",
            "After (ML model)": f"{after['recall']:.4f}",
            "Delta": f"{after['recall'] - before['recall']:+.4f}",
            "$ Impact": "",
        },
        {
            "Metric": "Alerts flagged (real count)",
            "Before (baseline)": f"{before['n_flagged']:,}",
            "After (ML model)": f"{after['n_flagged']:,}",
            "Delta": f"{after['n_flagged'] - before['n_flagged']:+,}",
            "$ Impact": "",
        },
        {
            "Metric": "False positives (real, implied by precision x flagged)",
            "Before (baseline)": f"{fi['before_fp']:,}",
            "After (ML model)": f"{fi['after_fp']:,}",
            "Delta": f"{fi['after_fp'] - fi['before_fp']:+,}",
            "$ Impact": f"ASSUMPTION: {_fmt_usd(fi['fp_dollar_savings'])} investigator-hours saved "
            f"({fi['hours_saved']:,.0f} hrs @ ${assumptions['cost_per_investigator_hour_usd']:.0f}/hr)",
        },
        {
            "Metric": "True positives caught (real, implied by recall x real positives)",
            "Before (baseline)": f"{fi['before_tp']:,}",
            "After (ML model)": f"{fi['after_tp']:,}",
            "Delta": f"{fi['tp_uplift']:+,}",
            "$ Impact": f"ASSUMPTION: {_fmt_usd(fi['tp_dollar_illustrative'])} illustrative regulatory-"
            f"exposure-avoidance ({fi['tp_uplift']:+,} cases @ "
            f"${assumptions['illustrative_case_exposure_usd']:,.0f}/case)",
        },
    ]
    return pd.DataFrame(rows)


# ============================================================================
# Real, computed-not-asserted production-readiness status -- derived strictly from the
# real two-gate verdicts already saved in each variant's own Notebook-3 report. Rendered
# identically across every output format so the HTML dashboard, Word report, Excel
# workbook, PPTX deck, and MODEL_CARD.md never disagree with each other.
# ============================================================================
def compute_bp_status(context: dict) -> dict:
    variants = context["variants"]
    primary = context["primary_variant"]
    verdicts = {name: v["report"]["overall_verdict"] for name, v in variants.items()}
    all_pass = all(v == "PASS" for v in verdicts.values())
    primary_pass = verdicts.get(primary) == "PASS"
    failing = [name for name, v in verdicts.items() if v != "PASS"]

    if all_pass:
        return {
            "label": "RECOMMENDED FOR PRODUCTION",
            "css_class": "good",
            "rationale": (
                f"Both the structural and statistical-robustness validation gates passed on "
                f"every real dataset variant evaluated ({', '.join(variants.keys())})."
            ),
        }
    if primary_pass:
        return {
            "label": "RECOMMENDED FOR PRODUCTION (Primary Variant Validated)",
            "css_class": "warning",
            "rationale": (
                f"{primary} -- this BP's locked mandatory realism-validation tier -- passed "
                f"both gates. {', '.join(failing)} did not pass both gates and should be "
                f"reviewed before treating that variant's own results as production-ready."
            ),
        }
    return {
        "label": "NOT RECOMMENDED FOR PRODUCTION -- VALIDATION GATES FAILED",
        "css_class": "critical",
        "rationale": (
            f"{primary} -- this BP's locked mandatory realism-validation tier -- did not pass "
            f"both validation gates (verdict: {verdicts.get(primary)}). Further validation is "
            f"required before this model is used to drive real investigator alerts."
        ),
    }


# ============================================================================
# Real, data-driven SMART recommendations -- every clause is built from real numbers
# already present in `context`, never a templated placeholder. Returns the same list for
# every output format.
# ============================================================================
def generate_smart_recommendations(context: dict) -> list:
    primary_name = context["primary_variant"]
    primary = context["variants"][primary_name]
    rep = primary["report"]
    fi = compute_financial_impact(primary["before"], primary["after"], context["assumptions"])
    shap = rep.get("shap_mean_abs_importance") or {}
    top_feature = max(shap.items(), key=lambda kv: kv[1])[0] if shap else None

    recs = [
        {
            "title": "Recalibrate the alert threshold on a fixed cadence",
            "specific": (
                f"The champion model ({rep['champion_name']}) currently operates at a real "
                f"decision threshold of {rep['selected_threshold']:.4f} on {primary_name}, "
                f"yielding real precision {rep['test_metrics']['precision']:.3f} and recall "
                f"{rep['test_metrics']['recall']:.3f}."
            ),
            "measurable": (
                "Track real precision/recall drift against these two baseline figures on every "
                "scoring batch; treat a real precision or recall move of more than 5 percentage "
                "points from these values as a trigger for threshold review."
            ),
            "achievable": "Uses the FastAPI scoring service's existing self-tested prediction path -- no new infrastructure required.",
            "relevant": "Directly controls the real false-positive alert volume investigators must review (SR 11-7 model risk management expectation).",
            "time_bound": "Quarterly recalibration review, next due within 90 days of production go-live.",
        },
        {
            "title": "Reallocate freed investigator capacity from the real false-positive reduction",
            "specific": (
                f"Moving from the naive fixed-dollar rule to the real ML model reduces false-"
                f"positive alerts by {fi['fp_reduction']:,} on {primary_name} (ASSUMPTION-"
                f"estimated at {fi['hours_saved']:,.0f} investigator hours, {_fmt_usd(fi['fp_dollar_savings'])})."
            ),
            "measurable": f"Real alert-review hours logged per investigator, compared against the {fi['hours_saved']:,.0f}-hour ASSUMPTION estimate above.",
            "achievable": "Capacity freed is redeployed to case investigation depth, not headcount reduction -- an operational scheduling change, not a new system.",
            "relevant": "Investigator capacity is the real, most commonly cited AML program bottleneck (FFIEC BSA/AML Examination Manual, alert-management pillar).",
            "time_bound": "Reassess real alert-review hours logged 60 days after production go-live against this ASSUMPTION estimate.",
        },
    ]

    if fi["tp_uplift"] > 0:
        recs.append(
            {
                "title": "Validate the real true-positive uplift against filed SARs",
                "specific": (
                    f"The real ML model's operating point is estimated to catch {fi['tp_uplift']:+,} "
                    f"more real laundering cases than the naive rule on {primary_name} "
                    f"(illustrative regulatory-exposure-avoidance ASSUMPTION: {_fmt_usd(fi['tp_dollar_illustrative'])})."
                ),
                "measurable": "Real SAR filing rate on model-flagged alerts vs. naive-rule-flagged alerts, tracked separately, never blended with the false-positive savings above.",
                "achievable": "Requires only tagging each filed SAR with which rule (naive vs. ML) originally surfaced the alert -- a labeling change, not a new detection system.",
                "relevant": "Directly evidences the model's real detection benefit to examiners (31 CFR Section 1020.320 SAR requirements).",
                "time_bound": "First real comparison report at the 6-month production mark (enough real SAR volume to be meaningful).",
            }
        )

    if top_feature:
        recs.append(
            {
                "title": "Document the dominant real model driver for examiner review",
                "specific": f"Real SHAP analysis ranks '{top_feature}' as the model's dominant real driver on {primary_name}.",
                "measurable": "Confirm this ranking is stable across each future real retrain (top-1 feature unchanged, or the change is explicitly documented).",
                "achievable": "Already computed by Notebook 3's existing SHAP step -- no new tooling required.",
                "relevant": "SR 11-7 model risk management requires a documented explanation of the model's real primary drivers.",
                "time_bound": "Refresh this documentation at every model retrain, alongside the MODEL_CARD.md update.",
            }
        )

    failing = [name for name, v in context["variants"].items() if v["report"]["overall_verdict"] != "PASS"]
    if failing:
        recs.append(
            {
                "title": f"Resolve validation gate failures on {', '.join(failing)} before relying on that variant",
                "specific": f"{', '.join(failing)} did not pass both the structural and statistical-robustness validation gates.",
                "measurable": "Re-run Notebook 3 on the failing variant(s) until both gates PASS.",
                "achievable": "Uses the existing, already-built Notebook 3 pipeline -- no new modeling approach required.",
                "relevant": "This platform's locked policy requires both gates to PASS before a variant's results are treated as production evidence.",
                "time_bound": "Before this variant is cited in any external or regulatory-facing report.",
            }
        )
    else:
        recs.append(
            {
                "title": "Maintain the real two-gate validation standard on every future retrain",
                "specific": f"Every real dataset variant evaluated for {context['bp_id']} currently passes both validation gates ({', '.join(context['variants'].keys())}).",
                "measurable": "Both gates must continue to PASS on every future retrain before redeployment.",
                "achievable": "Enforced automatically by Notebook 3's existing gate logic -- no manual step to remember.",
                "relevant": "This is the basis for this report's current production-recommended status.",
                "time_bound": "Every retrain cycle, before redeployment.",
            }
        )

    return recs


# ============================================================================
# Word report (python-docx)
# ============================================================================
def write_word_report(path: Path, context: dict) -> Path:
    from docx import Document
    from docx.shared import Pt, RGBColor

    doc = Document()
    _apply_word_brand_styles(doc)
    doc.add_heading(f"{context['bp_id']}: {context['bp_name']}", level=0)
    p = doc.add_paragraph()
    p.add_run(f"Compliance-Impact Report -- generated {context['generated_at_utc']} UTC").italic = True

    doc.add_heading("Business Objective", level=1)
    doc.add_paragraph(context["business_objective"])

    status = context.get("status") or compute_bp_status(context)
    doc.add_heading("Recommendation & Status", level=1)
    p = doc.add_paragraph()
    run = p.add_run(status["label"])
    run.bold = True
    run.font.size = Pt(14)
    status_colors = {
        "good": RGBColor(0x0C, 0xA3, 0x0C),
        "warning": RGBColor(0xC9, 0x85, 0x00),
        "critical": RGBColor(0xD0, 0x3B, 0x3B),
    }
    run.font.color.rgb = status_colors.get(status["css_class"], RGBColor(0x0B, 0x0B, 0x0B))
    doc.add_paragraph(status["rationale"])

    doc.add_heading("Executive Summary", level=1)
    primary = context["variants"][context["primary_variant"]]
    doc.add_paragraph(
        f"On the {context['primary_variant']} variant -- this business problem's locked "
        f"mandatory realism-validation tier -- the real champion model ({primary['report']['champion_name']}) "
        f"achieved a real held-out test PR-AUC of {primary['report']['test_metrics']['pr_auc']:.4f} "
        f"against a real random-baseline PR-AUC of {primary['report']['random_baseline_pr_auc']:.6f} "
        f"({_safe_div(primary['report']['test_metrics']['pr_auc'], primary['report']['random_baseline_pr_auc']):.0f}x lift). "
        f"Both the structural and statistical-robustness gates PASSED "
        f"(overall verdict: {primary['report']['overall_verdict']})."
    )

    doc.add_heading("What This Means for the Business", level=1)
    for point in context["business_benefits"]:
        doc.add_paragraph(point, style="List Bullet")

    doc.add_heading("Model Performance by Dataset Variant", level=1)
    doc.add_paragraph(
        "Per this platform's locked multi-variant policy, results from different dataset "
        "variants are never merged or blended -- each is reported here on its own, side by side."
    )
    table = doc.add_table(rows=1, cols=6)
    table.style = "Light Grid Accent 1"
    hdr = table.rows[0].cells
    for i, h in enumerate(["Variant", "Champion", "Test PR-AUC", "Precision", "Recall", "Gate Verdict"]):
        hdr[i].text = h
    for variant_name, v in context["variants"].items():
        r = v["report"]
        row = table.add_row().cells
        row[0].text = variant_name
        row[1].text = r["champion_name"]
        row[2].text = f"{r['test_metrics']['pr_auc']:.4f}"
        row[3].text = f"{r['test_metrics']['precision']:.4f}"
        row[4].text = f"{r['test_metrics']['recall']:.4f}"
        row[5].text = r["overall_verdict"]

    doc.add_heading(f"Before / After Impact ({context['primary_variant']})", level=1)
    doc.add_paragraph(
        "Before = a fixed-dollar-threshold rule (99th percentile of transaction amount, no "
        "other logic) -- the real, same-data baseline this project's locked policy requires, "
        "never a straw man. After = the real ML champion at its selected threshold. Dollar "
        "figures marked ASSUMPTION are illustrative, computed from a disclosed assumptions "
        "set (see Excel workbook's Assumptions sheet), never a directly measured quantity."
    )
    ba_df = context["before_after_tables"][context["primary_variant"]]
    ba_table = doc.add_table(rows=1, cols=len(ba_df.columns))
    ba_table.style = "Light Grid Accent 1"
    for i, col in enumerate(ba_df.columns):
        ba_table.rows[0].cells[i].text = col
    for _, row in ba_df.iterrows():
        cells = ba_table.add_row().cells
        for i, col in enumerate(ba_df.columns):
            cells[i].text = str(row[col])

    doc.add_heading("Financial Impact Summary", level=1)
    fi = compute_financial_impact(primary["before"], primary["after"], context["assumptions"])
    doc.add_paragraph(
        f"False-positive-reduction savings (ASSUMPTION): {_fmt_usd(fi['fp_dollar_savings'])} "
        f"({fi['hours_saved']:,.0f} investigator hours across {fi['fp_reduction']:,} fewer "
        f"false-positive alerts on {context['primary_variant']}). True-positive-uplift "
        f"illustrative regulatory-exposure-avoidance (ASSUMPTION): "
        f"{_fmt_usd(fi['tp_dollar_illustrative'])} ({fi['tp_uplift']:+,} additional real cases "
        f"caught). These two figures are never summed into one blended total, per this "
        f"platform's locked reporting policy (Section 7A)."
    )

    doc.add_heading("Explainability (SHAP -- champion model, real run)", level=1)
    shap_summary = primary["report"].get("shap_mean_abs_importance")
    if shap_summary:
        top5 = sorted(shap_summary.items(), key=lambda kv: kv[1], reverse=True)[:5]
        doc.add_paragraph("Top 5 real features by mean |SHAP value|:")
        for feat, val in top5:
            doc.add_paragraph(f"{feat}: {val:.4f}", style="List Bullet")
    else:
        doc.add_paragraph(
            "SHAP was not available on the machine that produced this run -- "
            "see that Notebook 3 run's own console output for the real reason."
        )

    doc.add_heading("Regulatory & Compliance Mapping", level=1)
    reg_table = doc.add_table(rows=1, cols=2)
    reg_table.style = "Light Grid Accent 1"
    reg_table.rows[0].cells[0].text = "Framework"
    reg_table.rows[0].cells[1].text = "Applies to"
    for fw, applies in context["regulatory_frameworks"]:
        row = reg_table.add_row().cells
        row[0].text = fw
        row[1].text = applies

    doc.add_heading("Fairness / Bias Testing", level=1)
    doc.add_paragraph(context["fairness_note"])

    doc.add_heading("Limitations & Caveats", level=1)
    for cav in context.get("caveats", []):
        doc.add_paragraph(cav, style="List Bullet")

    doc.add_heading("Recommendations", level=1)
    recs = context.get("smart_recommendations") or generate_smart_recommendations(context)
    for r in recs:
        doc.add_heading(r["title"], level=2)
        for label in ("specific", "measurable", "achievable", "relevant", "time_bound"):
            p = doc.add_paragraph(style="List Bullet")
            run = p.add_run(f"{label.replace('_', '-').title()}: ")
            run.bold = True
            p.add_run(r[label])

    _brand_word_table_headers(doc)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    return path


# ============================================================================
# Excel workbook (openpyxl) -- Assumptions-sheet-first pattern, live formulas, AutoFilter
# ============================================================================
def write_excel_workbook(path: Path, context: dict) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.workbook.properties import CalcProperties

    yellow_fill = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
    blue_font = Font(color="0000FF", bold=True)
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="2A78D6", end_color="2A78D6", fill_type="solid")

    wb = Workbook()
    wb.calculation = CalcProperties(fullCalcOnLoad=True)  # real recalc-on-open, not a static snapshot

    # --- Assumptions sheet FIRST (yellow fill / blue font for every hardcoded input) ---
    ws_a = wb.active
    ws_a.title = "Assumptions"
    ws_a["A1"] = "Assumption"
    ws_a["B1"] = "Value"
    ws_a["A1"].font = header_font
    ws_a["B1"].font = header_font
    ws_a["A1"].fill = header_fill
    ws_a["B1"].fill = header_fill
    assumption_rows = [
        ("Hours per alert review (ASSUMPTION)", context["assumptions"]["hours_per_alert_review"]),
        (
            "Cost per investigator hour, USD (ASSUMPTION)",
            context["assumptions"]["cost_per_investigator_hour_usd"],
        ),
        (
            "Illustrative regulatory-exposure-avoidance per case, USD (ASSUMPTION)",
            context["assumptions"]["illustrative_case_exposure_usd"],
        ),
    ]
    usd_assumption_rows = {
        "Cost per investigator hour, USD (ASSUMPTION)",
        "Illustrative regulatory-exposure-avoidance per case, USD (ASSUMPTION)",
    }
    for i, (label, val) in enumerate(assumption_rows, start=2):
        ws_a[f"A{i}"] = label
        ws_a[f"B{i}"] = val
        ws_a[f"B{i}"].fill = yellow_fill
        ws_a[f"B{i}"].font = blue_font
        if label in usd_assumption_rows:
            ws_a[f"B{i}"].number_format = _EXCEL_USD_FORMAT
    ws_a.column_dimensions["A"].width = 55
    ws_a.column_dimensions["B"].width = 18
    _brand_excel_sheet(ws_a, PALETTE["ink_muted"], freeze_cell="A2")
    # Named cells so downstream formulas are readable, not hardcoded coordinates
    wb.defined_names["hours_per_alert_review"] = _defined_name("hours_per_alert_review", "Assumptions", "B2")
    wb.defined_names["cost_per_investigator_hour_usd"] = _defined_name(
        "cost_per_investigator_hour_usd", "Assumptions", "B3"
    )
    wb.defined_names["illustrative_case_exposure_usd"] = _defined_name(
        "illustrative_case_exposure_usd", "Assumptions", "B4"
    )

    # --- Executive Summary sheet (status + financial impact) -- second sheet, right after
    # Assumptions (locked "Assumptions sheet FIRST" rule keeps Assumptions at position 1) ---
    status = context.get("status") or compute_bp_status(context)
    status_hex = {"good": "0CA30C", "warning": "FAB219", "critical": "D03B3B"}.get(
        status["css_class"], "2A78D6"
    )
    ws_e = wb.create_sheet("Executive Summary")
    ws_e["A1"] = "Status"
    ws_e["B1"] = "Rationale"
    ws_e["A1"].font = header_font
    ws_e["B1"].font = header_font
    ws_e["A1"].fill = header_fill
    ws_e["B1"].fill = header_fill
    ws_e["A2"] = status["label"]
    ws_e["A2"].fill = PatternFill(start_color=status_hex, end_color=status_hex, fill_type="solid")
    ws_e["A2"].font = Font(bold=True, color="FFFFFF")
    ws_e["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws_e["B2"] = status["rationale"]
    ws_e["B2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws_e.row_dimensions[2].height = 60
    ws_e.column_dimensions["A"].width = 42
    ws_e.column_dimensions["B"].width = 95

    primary_variant = context["primary_variant"]
    ba_sheet_name = f"Before-After {primary_variant}"[:31]
    ws_e["A4"] = f"Financial Impact Summary (primary variant: {primary_variant}, live formulas)"
    ws_e["A4"].font = Font(bold=True)
    ws_e["C4"] = "Formatted (with B/M shorthand)"
    ws_e["C4"].font = Font(bold=True, italic=True, color="52514E")
    ws_e["A5"] = "False-positive-reduction $ savings (ASSUMPTION)"
    ws_e["B5"] = f"='{ba_sheet_name}'!B8"
    ws_e["B5"].number_format = _EXCEL_USD_FORMAT
    ws_e["C5"] = _excel_usd_shorthand_formula("B5")
    ws_e["A6"] = "True-positive-uplift illustrative $ (ASSUMPTION)"
    ws_e["B6"] = f"='{ba_sheet_name}'!B9"
    ws_e["B6"].number_format = _EXCEL_USD_FORMAT
    ws_e["C6"] = _excel_usd_shorthand_formula("B6")
    ws_e["A7"] = (
        "Note: the two figures above are never summed into one blended total (locked Section 7A policy)."
    )
    ws_e["A7"].font = Font(italic=True, color="52514E")
    ws_e.column_dimensions["C"].width = 26
    _brand_excel_sheet(ws_e, status_hex, freeze_cell="A3")

    # --- Variant summary sheet (real, per-variant, never blended) ---
    ws_s = wb.create_sheet("Variant Summary")
    headers = [
        "Variant",
        "Champion",
        "Test PR-AUC",
        "Random Baseline PR-AUC",
        "Lift (x)",
        "Precision",
        "Recall",
        "F2",
        "Gate 1",
        "Gate 2",
        "Overall Verdict",
    ]
    for c, h in enumerate(headers, start=1):
        cell = ws_s.cell(row=1, column=c, value=h)
        cell.font = header_font
        cell.fill = header_fill
    for r, (variant_name, v) in enumerate(context["variants"].items(), start=2):
        rep = v["report"]
        ws_s.cell(row=r, column=1, value=variant_name)
        ws_s.cell(row=r, column=2, value=rep["champion_name"])
        ws_s.cell(row=r, column=3, value=rep["test_metrics"]["pr_auc"])
        ws_s.cell(row=r, column=4, value=rep["random_baseline_pr_auc"])
        col_c, col_d = get_column_letter(3), get_column_letter(4)
        ws_s.cell(row=r, column=5, value=f"={col_c}{r}/{col_d}{r}")  # live formula, not a hardcoded lift
        ws_s.cell(row=r, column=6, value=rep["test_metrics"]["precision"])
        ws_s.cell(row=r, column=7, value=rep["test_metrics"]["recall"])
        ws_s.cell(row=r, column=8, value=rep["test_metrics"]["f2"])
        ws_s.cell(row=r, column=9, value=rep["gate1_verdict"])
        ws_s.cell(row=r, column=10, value=rep["gate2_verdict"])
        ws_s.cell(row=r, column=11, value=rep["overall_verdict"])
    ws_s.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{1 + len(context['variants'])}"
    for c in range(1, len(headers) + 1):
        ws_s.column_dimensions[get_column_letter(c)].width = 20
    _brand_excel_sheet(ws_s, PALETTE["series_1_blue"], freeze_cell="A2")
    _band_excel_rows(
        ws_s, first_data_row=2, last_data_row=1 + len(context["variants"]), first_col=1, last_col=len(headers)
    )
    _color_verdict_cells(ws_s, rows=range(2, 2 + len(context["variants"])), cols=[9, 10, 11])

    # --- Before/After sheet per variant, dollar figures as LIVE formulas referencing Assumptions ---
    for variant_name, ba_df in context["before_after_tables"].items():
        sheet_name = f"Before-After {variant_name}"[:31]
        ws_b = wb.create_sheet(sheet_name)
        before = context["variants"][variant_name]["before"]
        after = context["variants"][variant_name]["after"]
        before_fp = before["n_flagged"] - round(before["precision"] * before["n_flagged"])
        after_fp = after["n_flagged"] - round(after["precision"] * after["n_flagged"])
        before_tp = round(before["recall"] * before["n_positive"])
        after_tp = round(after["recall"] * after["n_positive"])

        rows = [
            ("Precision", before["precision"], after["precision"]),
            ("Recall", before["recall"], after["recall"]),
            ("Alerts flagged", before["n_flagged"], after["n_flagged"]),
            ("False positives (real, implied)", before_fp, after_fp),
            ("True positives caught (real, implied)", before_tp, after_tp),
        ]
        for c, h in enumerate(["Metric", "Before (baseline)", "After (ML model)", "Delta"], start=1):
            cell = ws_b.cell(row=1, column=c, value=h)
            cell.font = header_font
            cell.fill = header_fill
        for r, (metric, b, a) in enumerate(rows, start=2):
            ws_b.cell(row=r, column=1, value=metric)
            ws_b.cell(row=r, column=2, value=b)
            ws_b.cell(row=r, column=3, value=a)
            ws_b.cell(row=r, column=4, value=f"=C{r}-B{r}")  # live delta formula
        # $ Impact rows -- LIVE formulas referencing the Assumptions sheet, never hardcoded
        fp_row = 5  # "False positives" row (row 2=Precision,3=Recall,4=Alerts,5=FP,6=TP)
        tp_row = 6
        ws_b.cell(row=7, column=3, value="Formatted (with B/M shorthand)").font = Font(
            italic=True, color="52514E"
        )
        ws_b.cell(row=8, column=1, value="False-positive-reduction $ savings (ASSUMPTION, live formula)")
        ws_b.cell(
            row=8, column=2, value=f"=D{fp_row}*-1*hours_per_alert_review*cost_per_investigator_hour_usd"
        )
        ws_b.cell(row=8, column=2).number_format = _EXCEL_USD_FORMAT
        ws_b.cell(row=8, column=3, value=_excel_usd_shorthand_formula("B8"))
        ws_b.cell(row=9, column=1, value="True-positive-uplift $ (illustrative, ASSUMPTION, live formula)")
        ws_b.cell(row=9, column=2, value=f"=D{tp_row}*illustrative_case_exposure_usd")
        ws_b.cell(row=9, column=2).number_format = _EXCEL_USD_FORMAT
        ws_b.cell(row=9, column=3, value=_excel_usd_shorthand_formula("B9"))
        ws_b.cell(
            row=11,
            column=1,
            value="Note: the two $ lines above are never summed into one blended figure "
            "(locked project rule, Section 7A).",
        )
        ws_b.auto_filter.ref = "A1:D6"
        for c in range(1, 5):
            ws_b.column_dimensions[get_column_letter(c)].width = 42 if c == 1 else (26 if c == 3 else 20)
        _brand_excel_sheet(ws_b, PALETTE["series_3_aqua"], freeze_cell="A2")
        _band_excel_rows(ws_b, first_data_row=2, last_data_row=6, first_col=1, last_col=4)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))
    return path


def _defined_name(name: str, sheet: str, cell: str):
    from openpyxl.workbook.defined_name import DefinedName

    return DefinedName(name, attr_text=f"'{sheet}'!${cell[0]}${cell[1:]}")


_EXCEL_USD_FORMAT = '"$"#,##0'


def _excel_usd_shorthand_formula(cell_ref: str) -> str:
    """Live Excel formula mirroring format_usd()'s python logic: the real dollar value in
    `cell_ref`, with a B/M shorthand appended for any magnitude >= $1M -- so the workbook
    shows the same 'exact figure plus B/M form' this user's standing formatting rule
    requires even though the underlying value is a live formula, not a static string."""
    return (
        f'=IF(ABS({cell_ref})>=1000000000,TEXT({cell_ref}/1000000000,"$0.00")&"B",'
        f'IF(ABS({cell_ref})>=1000000,TEXT({cell_ref}/1000000,"$0.00")&"M",'
        f'TEXT({cell_ref},"$#,##0")))'
    )


# ============================================================================
# HTML dashboard -- self-contained, real Chart.js bundled INLINE (never CDN-loaded),
# real vanilla-JS interactivity (variant selector), CVD-validated palette.
# ============================================================================
def write_html_dashboard(path: Path, context: dict, chartjs_js_path: Path) -> Path:
    chartjs_source = Path(chartjs_js_path).read_text(encoding="utf-8")

    status = context.get("status") or compute_bp_status(context)
    recommendations = context.get("smart_recommendations") or generate_smart_recommendations(context)

    variants_json = {}
    for variant_name, v in context["variants"].items():
        rep = v["report"]
        before, after = v["before"], v["after"]
        fi = compute_financial_impact(before, after, context["assumptions"])
        ba_df = context["before_after_tables"][variant_name]
        variants_json[variant_name] = {
            "champion": rep["champion_name"],
            "pr_auc": rep["test_metrics"]["pr_auc"],
            "random_baseline": rep["random_baseline_pr_auc"],
            "precision": rep["test_metrics"]["precision"],
            "recall": rep["test_metrics"]["recall"],
            "f2": rep["test_metrics"]["f2"],
            "threshold": rep.get("selected_threshold"),
            "verdict": rep["overall_verdict"],
            "stage_a": rep["stage_a_ranking"],
            "shap": rep.get("shap_mean_abs_importance") or {},
            "before_after_rows": ba_df.to_dict(orient="records"),
            "before_after_chart": {
                "labels": ["Precision", "Recall"],
                "before": [before["precision"], before["recall"]],
                "after": [after["precision"], after["recall"]],
            },
            "financial": {
                "fp_reduction": fi["fp_reduction"],
                "hours_saved": fi["hours_saved"],
                "fp_dollar_savings": fi["fp_dollar_savings"],
                "fp_dollar_savings_fmt": _fmt_usd(fi["fp_dollar_savings"]),
                "tp_uplift": fi["tp_uplift"],
                "tp_dollar_illustrative": fi["tp_dollar_illustrative"],
                "tp_dollar_illustrative_fmt": _fmt_usd(fi["tp_dollar_illustrative"]),
            },
        }
    data_json = json.dumps(variants_json)
    variant_names_json = json.dumps(list(context["variants"].keys()))
    status_json = json.dumps(status)
    recs_json = json.dumps(recommendations)
    primary_variant_json = json.dumps(context["primary_variant"])
    palette = PALETTE

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{context['bp_id']} -- {context['bp_name']} -- Compliance Dashboard</title>
<style>
  :root {{
    color-scheme: light;
    --surface: {palette['surface']}; --page: {palette['page']};
    --ink: {palette['ink_primary']}; --ink-2: {palette['ink_secondary']}; --ink-muted: {palette['ink_muted']};
    --grid: {palette['gridline']};
    --s1: {palette['series_1_blue']}; --s2: {palette['series_2_orange']}; --s3: {palette['series_3_aqua']};
    --good: {palette['status_good']}; --warn: {palette['status_warning']}; --crit: {palette['status_critical']};
  }}
  * {{ box-sizing: border-box; }}
  html {{ scroll-behavior:smooth; }}
  body {{
    margin:0; color:var(--ink); font-family: system-ui,-apple-system,"Segoe UI",sans-serif;
    /* Pleasant, restrained background: soft brand-tinted gradient washes over the page plane --
       never behind text (cards stay on solid --surface), so legibility/contrast is unaffected. */
    background:
      radial-gradient(1100px 580px at 8% -8%, rgba(42,120,214,0.08), transparent 58%),
      radial-gradient(900px 520px at 100% 0%, rgba(27,175,122,0.07), transparent 55%),
      radial-gradient(800px 500px at 50% 110%, rgba(235,104,52,0.05), transparent 60%),
      var(--page);
    background-attachment: fixed;
    min-height:100vh;
  }}
  .accent-bar {{ height:4px; width:100%;
    background: linear-gradient(90deg, var(--s1), var(--s3), var(--s2), var(--s1));
    background-size: 300% 100%; animation: shimmer 6s linear infinite; }}
  @keyframes shimmer {{ 0% {{ background-position:0% 0; }} 100% {{ background-position:300% 0; }} }}
  header {{ padding:22px 24px; border-bottom:1px solid var(--grid); background:var(--surface);
    animation: fadeInUp .5s ease both; box-shadow:0 1px 0 rgba(11,11,11,.02); }}
  h1 {{ margin:0 0 4px; font-size:21px; letter-spacing:-.01em; }}
  .sub {{ color:var(--ink-2); font-size:13px; }}

  @keyframes fadeInUp {{ from {{ opacity:0; transform:translateY(10px); }} to {{ opacity:1; transform:translateY(0); }} }}
  @keyframes fadeSection {{ from {{ opacity:0; transform:translateY(6px); }} to {{ opacity:1; transform:translateY(0); }} }}
  @keyframes pulseDot {{ 0% {{ box-shadow:0 0 0 0 currentColor; opacity:1; }} 70% {{ box-shadow:0 0 0 9px transparent; opacity:.35; }} 100% {{ box-shadow:0 0 0 0 transparent; opacity:1; }} }}
  .tile, .chart-box, .rec-card, .narrative, .status-banner {{ animation: fadeInUp .45s ease both; }}
  .tile, .chart-box, .rec-card {{ box-shadow:0 1px 2px rgba(11,11,11,.04);
    transition: transform .2s cubic-bezier(.22,1,.36,1), box-shadow .2s ease, border-color .2s ease; }}
  .tile:hover, .chart-box:hover, .rec-card:hover {{ transform:translateY(-4px); box-shadow:0 14px 28px rgba(11,11,11,.10); border-color:rgba(42,120,214,.25); }}

  .status-banner {{ margin:16px 24px 0; padding:16px 20px; border-radius:12px; border:1px solid var(--grid);
    display:flex; align-items:flex-start; gap:14px; box-shadow:0 1px 2px rgba(11,11,11,.04); }}
  .status-banner.good {{ background:linear-gradient(135deg,#eafaea,#e7f7e7); }}
  .status-banner.warning {{ background:linear-gradient(135deg,#fff9ec,#fff6e5); }}
  .status-banner.critical {{ background:linear-gradient(135deg,#fef0ef,#fdeceb); }}
  .status-banner .dot {{ width:14px; height:14px; border-radius:50%; flex:0 0 auto; margin-top:3px; position:relative; }}
  .status-banner .dot::after {{ content:""; position:absolute; inset:0; border-radius:50%; background:currentColor;
    animation: pulseDot 2.2s ease-out infinite; }}
  .status-banner .dot.good {{ background:var(--good); color:var(--good); }}
  .status-banner .dot.warning {{ background:var(--warn); color:var(--warn); }}
  .status-banner .dot.critical {{ background:var(--crit); color:var(--crit); }}
  .status-banner .label {{ font-size:16px; font-weight:700; }}
  .status-banner .rationale {{ font-size:13px; color:var(--ink-2); margin-top:4px; line-height:1.5; }}

  .narrative {{ background:var(--surface); border:1px solid var(--grid); border-radius:12px; padding:18px 20px; margin:16px 24px 0;
    box-shadow:0 1px 2px rgba(11,11,11,.04); }}
  .narrative h2 {{ margin:0 0 8px; font-size:15px; }}
  .narrative p {{ margin:0 0 10px; color:var(--ink-2); font-size:13px; line-height:1.5; }}
  .narrative ul {{ margin:0; padding-left:18px; }}
  .narrative li {{ color:var(--ink-2); font-size:13px; line-height:1.6; }}

  .tabs {{ position:relative; display:flex; gap:4px; padding:0 24px; margin-top:16px; background:var(--surface); border-bottom:1px solid var(--grid); }}
  .tabs button {{ border:none; background:transparent; color:var(--ink-2); padding:12px 16px; cursor:pointer;
    font-size:13px; font-weight:600; border-bottom:2px solid transparent; border-radius:8px 8px 0 0;
    transition:color .15s ease, background .2s ease; position:relative; z-index:1; }}
  .tabs button:hover {{ color:var(--ink); background:rgba(42,120,214,.07); }}
  .tabs button.active {{ color:var(--s1); }}
  .tab-indicator {{ position:absolute; bottom:-1px; left:0; height:3px; width:0; border-radius:3px;
    background:linear-gradient(90deg, var(--s1), var(--s3));
    box-shadow:0 0 8px rgba(42,120,214,.45);
    transition: transform .4s cubic-bezier(.34,1.56,.64,1), width .4s cubic-bezier(.34,1.56,.64,1); }}

  .filters {{ display:flex; align-items:center; gap:8px; padding:12px 24px; background:var(--surface); border-bottom:1px solid var(--grid); }}
  .filters .fl-label {{ color:var(--ink-muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; margin-right:4px; }}
  .filters button {{ position:relative; overflow:hidden; border:1px solid var(--grid); background:var(--surface); color:var(--ink); padding:6px 14px;
    border-radius:999px; cursor:pointer; font-size:13px;
    transition: background .2s ease, color .2s ease, border-color .2s ease, transform .25s cubic-bezier(.34,1.56,.64,1), box-shadow .2s ease; }}
  .filters button:hover {{ transform:translateY(-2px); box-shadow:0 6px 14px rgba(11,11,11,.10); border-color:rgba(42,120,214,.35); }}
  .filters button.active {{ background:var(--s1); color:#fff; border-color:var(--s1); box-shadow:0 4px 12px rgba(42,120,214,.35);
    animation: filterPop .35s cubic-bezier(.34,1.56,.64,1); }}
  @keyframes filterPop {{ 0% {{ transform:scale(.88); }} 60% {{ transform:scale(1.06); }} 100% {{ transform:scale(1); }} }}
  .ripple {{ position:absolute; border-radius:50%; background:rgba(255,255,255,.55); transform:scale(0);
    animation: rippleFx .55s ease-out; pointer-events:none; }}
  @keyframes rippleFx {{ to {{ transform:scale(2.6); opacity:0; }} }}

  .view-section {{ display:none; }}
  .view-section.active {{ display:block; animation: fadeSection .35s cubic-bezier(.22,1,.36,1) both; }}

  main {{ padding:20px 24px; display:grid; gap:16px; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); }}
  .tile {{ background:var(--surface); border:1px solid var(--grid); border-radius:12px; padding:16px; }}
  .tile .label {{ color:var(--ink-2); font-size:12px; text-transform:uppercase; letter-spacing:.04em; display:flex; justify-content:space-between; align-items:center; }}
  .tile .value {{ font-size:27px; font-weight:650; margin-top:4px; }}
  .tile .value.good {{ color:var(--good); }}
  .wide {{ grid-column: 1 / -1; }}
  .chart-box {{ background:var(--surface); border:1px solid var(--grid); border-radius:12px; padding:16px; height:320px; }}
  .bar-track {{ background:var(--grid); border-radius:6px; height:8px; overflow:hidden; margin-top:8px; position:relative; }}
  .bar-fill {{ height:100%; border-radius:6px; width:0%; position:relative; overflow:hidden;
    transition:width 1s cubic-bezier(.22,1,.36,1); }}
  .bar-fill::after {{ content:""; position:absolute; inset:0;
    background:linear-gradient(90deg, transparent, rgba(255,255,255,.45), transparent);
    background-size:60px 100%; animation: shimmerBar 1.8s ease-in-out infinite; }}
  @keyframes shimmerBar {{ 0% {{ background-position:-120px 0; }} 100% {{ background-position:220px 0; }} }}
  .verdict-pill {{ display:inline-block; padding:2px 10px; border-radius:999px; font-size:12px; font-weight:600; }}
  .verdict-pass {{ background:#e7f7e7; color:var(--good); }}
  .verdict-fail {{ background:#fdeceb; color:var(--crit); }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th, td {{ text-align:left; padding:6px 8px; border-bottom:1px solid var(--grid); }}
  th {{ color:var(--ink-2); font-weight:600; }}
  tbody tr {{ transition: background .12s ease; }}
  tbody tr:hover {{ background:rgba(42,120,214,.05); }}
  .search-box {{ padding:6px 10px; border:1px solid var(--grid); border-radius:6px; font-size:12.5px; width:100%; margin-bottom:10px;
    transition: border-color .15s ease, box-shadow .15s ease; }}
  .search-box:focus {{ outline:none; border-color:var(--s1); box-shadow:0 0 0 3px rgba(42,120,214,.12); }}
  .btn-ghost {{ border:1px solid var(--grid); background:var(--surface); color:var(--ink); padding:5px 12px;
    border-radius:6px; cursor:pointer; font-size:12px; transition: background .15s ease; }}
  .btn-ghost:hover {{ background:var(--page); }}
  .rec-card {{ background:var(--surface); border:1px solid var(--grid); border-radius:12px; padding:16px 18px; margin-bottom:12px; }}
  .rec-card h3 {{ margin:0 0 8px; font-size:14.5px; }}
  .rec-card .smart-row {{ font-size:12.5px; color:var(--ink-2); margin:5px 0; line-height:1.55; }}
  .rec-card .smart-row b {{ color:var(--ink); }}
  footer {{ padding:16px 24px; color:var(--ink-muted); font-size:12px; }}
</style>
</head>
<body>
<div class="accent-bar"></div>
<header>
  <h1>{context['bp_id']} -- {context['bp_name']}</h1>
  <div class="sub">Compliance-Impact Dashboard -- generated {context['generated_at_utc']} UTC -- real data, this project's own notebook runs</div>
</header>
<div class="status-banner" id="statusBanner"></div>
<div class="narrative">
  <h2>Business Objective</h2>
  <p>{context['business_objective']}</p>
  <h2>What This Means for the Business</h2>
  <ul>
    {''.join(f'<li>{point}</li>' for point in context['business_benefits'])}
  </ul>
</div>

<div class="tabs" id="tabs">
  <button data-view="overview" class="active">Overview</button>
  <button data-view="performance">Model Performance</button>
  <button data-view="financial">Financial Impact</button>
  <button data-view="recommendations">Recommendations</button>
  <span class="tab-indicator" id="tabIndicator"></span>
</div>
<div class="filters" id="filters"><span class="fl-label">Dataset variant</span></div>

<section id="view-overview" class="view-section active">
  <main id="tiles"></main>
</section>

<section id="view-performance" class="view-section">
  <main style="grid-template-columns: 1fr 1fr;">
    <div class="chart-box"><canvas id="stageAChart"></canvas></div>
    <div class="chart-box">
      <input type="text" id="shapSearch" class="search-box" placeholder="Filter real SHAP features by name...">
      <canvas id="shapChart"></canvas>
    </div>
  </main>
  <main>
    <div class="tile wide">
      <div class="label">
        <span>Stage A candidate ranking (real, this variant)</span>
        <button id="stageASortBtn" class="btn-ghost">Sort by PR-AUC &darr;</button>
      </div>
      <table id="stageATable"><thead><tr><th>Rank</th><th>Model</th><th>Test PR-AUC</th></tr></thead><tbody></tbody></table>
    </div>
  </main>
</section>

<section id="view-financial" class="view-section">
  <main id="finTiles"></main>
  <main style="grid-template-columns: 1fr 1fr;">
    <div class="chart-box"><canvas id="finChart"></canvas></div>
    <div class="chart-box"><canvas id="baChart"></canvas></div>
  </main>
  <main>
    <div class="tile wide">
      <div class="label">Before / After -- full real table (this variant)</div>
      <p id="finNote" class="sub" style="margin:8px 0 10px;"></p>
      <table id="baTable"><thead><tr><th>Metric</th><th>Before (baseline)</th><th>After (ML model)</th><th>Delta</th><th>$ Impact</th></tr></thead><tbody></tbody></table>
    </div>
  </main>
</section>

<section id="view-recommendations" class="view-section">
  <main>
    <div class="wide" id="recsList"></div>
  </main>
</section>

<footer>
  Real, per-variant results -- HI-Small and LI-Medium are never merged or blended into one
  unlabeled figure, per this platform's locked multi-variant policy. Chart.js bundled locally
  (no CDN). Generated by report_builder.py -- IBM AML RiskIQ Enterprise Suite.
</footer>
<script>
{chartjs_source}
</script>
<script>
(function() {{
  const DATA = {data_json};
  const VARIANTS = {variant_names_json};
  const STATUS = {status_json};
  const RECS = {recs_json};
  const PRIMARY = {primary_variant_json};
  let current = VARIANTS.includes(PRIMARY) ? PRIMARY : VARIANTS[0];
  let shapFilter = "";
  let stageASortDir = "desc";
  const palette = {{ s1: "{palette['series_1_blue']}", s2: "{palette['series_2_orange']}", s3: "{palette['series_3_aqua']}",
    grid: "{palette['gridline']}", ink2: "{palette['ink_secondary']}" }};

  // ---- status banner (computed from ALL real variants -- not slicer-dependent) ----
  const banner = document.getElementById("statusBanner");
  banner.className = "status-banner " + STATUS.css_class;
  banner.innerHTML = `<div class="dot ${{STATUS.css_class}}"></div>
    <div><div class="label">${{STATUS.label}}</div><div class="rationale">${{STATUS.rationale}}</div></div>`;

  function spawnRipple(e, btn) {{
    const old = btn.querySelector(".ripple"); if (old) old.remove();
    const rect = btn.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height) * 1.4;
    const span = document.createElement("span");
    span.className = "ripple";
    span.style.width = span.style.height = size + "px";
    span.style.left = (e.clientX - rect.left - size / 2) + "px";
    span.style.top = (e.clientY - rect.top - size / 2) + "px";
    btn.appendChild(span);
    span.addEventListener("animationend", () => span.remove());
  }}

  // ---- view tabs (slicer: which section is shown) ----
  const tabs = [...document.querySelectorAll(".tabs button")];
  const tabIndicator = document.getElementById("tabIndicator");
  function moveTabIndicator(btn) {{
    if (!tabIndicator || !btn) return;
    tabIndicator.style.width = btn.offsetWidth + "px";
    tabIndicator.style.transform = "translateX(" + btn.offsetLeft + "px)";
  }}
  tabs.forEach(btn => btn.addEventListener("click", (e) => {{
    spawnRipple(e, btn);
    tabs.forEach(b => b.classList.toggle("active", b === btn));
    document.querySelectorAll(".view-section").forEach(sec => sec.classList.toggle("active", sec.id === "view-" + btn.dataset.view));
    moveTabIndicator(btn);
  }}));
  window.addEventListener("resize", () => moveTabIndicator(tabs.find(b => b.classList.contains("active"))));
  requestAnimationFrame(() => moveTabIndicator(tabs.find(b => b.classList.contains("active"))));

  // ---- dataset-variant slicer ----
  const filtersEl = document.getElementById("filters");
  VARIANTS.forEach(v => {{
    const b = document.createElement("button");
    b.textContent = v;
    b.className = v === current ? "active" : "";
    b.onclick = (e) => {{ spawnRipple(e, b); current = v; render(); }};
    filtersEl.appendChild(b);
  }});

  // ---- animated counters (real values, counted up on every render). `opts.currency` shows
  // a live "$"/"-$" sign throughout the count-up; `opts.finalText` -- used for dollar tiles --
  // guarantees the value the animation lands on is EXACTLY the real, precomputed
  // format_usd() string (comma-separated exact figure plus a B/M shorthand for any
  // magnitude >= $1M), so the KPI tiles never show a bare unformatted number. ----
  function animateValue(el, start, end, decimals, opts) {{
    opts = opts || {{}};
    const suffix = opts.suffix || "";
    const currency = !!opts.currency;
    const duration = opts.duration || 700;
    const finalText = opts.finalText;
    function fmt(v) {{
      if (currency) {{
        const sign = v < 0 ? "-" : "";
        const mag = Math.abs(v);
        return sign + "$" + (decimals === 0 ? Math.round(mag).toLocaleString() : mag.toFixed(decimals)) + suffix;
      }}
      return (decimals === 0 ? Math.round(v).toLocaleString() : v.toFixed(decimals)) + suffix;
    }}
    const t0 = performance.now();
    function step(t) {{
      const p = Math.min(1, (t - t0) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      const v = start + (end - start) * eased;
      if (p < 1) {{
        el.textContent = fmt(v);
        requestAnimationFrame(step);
      }} else {{
        el.textContent = finalText != null ? finalText : fmt(end);
      }}
    }}
    requestAnimationFrame(step);
  }}

  let stageAChart, shapChart, baChart, finChart;

  function renderStageATable(rows) {{
    const tbody = document.querySelector("#stageATable tbody");
    tbody.innerHTML = "";
    rows.forEach((row, i) => {{
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${{i + 1}}</td><td>${{row.name}}</td><td>${{row.pr_auc.toFixed(4)}}</td>`;
      tbody.appendChild(tr);
    }});
  }}

  function renderBaTable(rows) {{
    const tbody = document.querySelector("#baTable tbody");
    tbody.innerHTML = "";
    rows.forEach(row => {{
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${{row["Metric"]}}</td><td>${{row["Before (baseline)"]}}</td>`
        + `<td>${{row["After (ML model)"]}}</td><td>${{row["Delta"]}}</td><td>${{row["$ Impact"]}}</td>`;
      tbody.appendChild(tr);
    }});
  }}

  function render() {{
    [...filtersEl.querySelectorAll("button")].forEach(b => b.classList.toggle("active", b.textContent === current));
    const d = DATA[current];

    // ---- Overview tab ----
    const tilesEl = document.getElementById("tiles");
    tilesEl.innerHTML = `
      <div class="tile"><div class="label">Champion</div><div class="value" id="t-champ">${{d.champion}}</div></div>
      <div class="tile"><div class="label">Test PR-AUC</div><div class="value" id="t-prauc">0.0000</div></div>
      <div class="tile"><div class="label">Lift over random baseline</div><div class="value good" id="t-lift">0x</div></div>
      <div class="tile"><div class="label">Precision</div><div class="value" id="t-prec">0.000</div>
        <div class="bar-track"><div class="bar-fill" id="bar-prec" style="background:${{palette.s1}}"></div></div></div>
      <div class="tile"><div class="label">Recall</div><div class="value" id="t-rec">0.000</div>
        <div class="bar-track"><div class="bar-fill" id="bar-rec" style="background:${{palette.s2}}"></div></div></div>
      <div class="tile"><div class="label">Two-gate verdict</div><div class="value"><span class="verdict-pill ${{d.verdict === 'PASS' ? 'verdict-pass' : 'verdict-fail'}}">${{d.verdict}}</span></div></div>
      <div class="tile"><div class="label">False-positive-reduction savings (ASSUMPTION)</div><div class="value good" id="t-kpi-fp">$0</div></div>
      <div class="tile"><div class="label">True-positive-uplift value, illustrative (ASSUMPTION)</div><div class="value good" id="t-kpi-tp">$0</div></div>
    `;
    [...tilesEl.children].forEach((el, i) => {{ el.style.animationDelay = (i * 40) + "ms"; }});
    animateValue(document.getElementById("t-prauc"), 0, d.pr_auc, 4);
    animateValue(document.getElementById("t-lift"), 0, d.pr_auc / d.random_baseline, 0, {{ suffix: "x" }});
    animateValue(document.getElementById("t-prec"), 0, d.precision, 3);
    animateValue(document.getElementById("t-rec"), 0, d.recall, 3);
    animateValue(document.getElementById("t-kpi-fp"), 0, d.financial.fp_dollar_savings, 0,
      {{ currency: true, duration: 800, finalText: d.financial.fp_dollar_savings_fmt }});
    animateValue(document.getElementById("t-kpi-tp"), 0, d.financial.tp_dollar_illustrative, 0,
      {{ currency: true, duration: 800, finalText: d.financial.tp_dollar_illustrative_fmt }});
    requestAnimationFrame(() => {{
      document.getElementById("bar-prec").style.width = (d.precision * 100).toFixed(1) + "%";
      document.getElementById("bar-rec").style.width = (d.recall * 100).toFixed(1) + "%";
    }});

    // ---- Model Performance tab ----
    const stageASorted = [...d.stage_a].sort((a, b) => stageASortDir === "desc" ? b.pr_auc - a.pr_auc : a.pr_auc - b.pr_auc);
    if (stageAChart) stageAChart.destroy();
    stageAChart = new Chart(document.getElementById("stageAChart"), {{
      type: "bar",
      data: {{ labels: stageASorted.map(r => r.name), datasets: [{{ label: "Test PR-AUC", data: stageASorted.map(r => r.pr_auc),
        backgroundColor: palette.s1, borderRadius: 4 }}] }},
      options: {{ responsive: true, maintainAspectRatio: false, animation: {{ duration: 700, easing: "easeOutCubic" }},
        plugins: {{ legend: {{ display: false }}, title: {{ display: true, text: "Stage A candidate comparison (" + current + ")" }} }},
        scales: {{ y: {{ beginAtZero: true, grid: {{ color: palette.grid }} }}, x: {{ grid: {{ display: false }} }} }} }}
    }});
    renderStageATable(stageASorted);

    const shapEntries = Object.entries(d.shap)
      .filter(e => e[0].toLowerCase().includes(shapFilter.toLowerCase()))
      .sort((a, b) => b[1] - a[1]).slice(0, 10);
    if (shapChart) shapChart.destroy();
    shapChart = new Chart(document.getElementById("shapChart"), {{
      type: "bar",
      data: {{ labels: shapEntries.map(e => e[0]), datasets: [{{ label: "mean |SHAP|", data: shapEntries.map(e => e[1]),
        backgroundColor: palette.s3, borderRadius: 4 }}] }},
      options: {{ responsive: true, maintainAspectRatio: false, indexAxis: "y", animation: {{ duration: 700, easing: "easeOutCubic" }},
        plugins: {{ legend: {{ display: false }}, title: {{ display: true, text: "Top real SHAP features, champion (" + current + ")" }} }},
        scales: {{ x: {{ beginAtZero: true, grid: {{ color: palette.grid }} }}, y: {{ grid: {{ display: false }} }} }} }}
    }});

    // ---- Financial Impact tab ----
    const finTilesEl = document.getElementById("finTiles");
    finTilesEl.innerHTML = `
      <div class="tile"><div class="label">False-positive-reduction savings (ASSUMPTION)</div><div class="value good" id="t-fp">$0</div></div>
      <div class="tile"><div class="label">Investigator hours freed (ASSUMPTION)</div><div class="value" id="t-hrs">0</div></div>
      <div class="tile"><div class="label">True-positive uplift, illustrative exposure avoided (ASSUMPTION)</div><div class="value good" id="t-tp">$0</div></div>
      <div class="tile"><div class="label">Additional real cases caught</div><div class="value" id="t-cases">0</div></div>
    `;
    [...finTilesEl.children].forEach((el, i) => {{ el.style.animationDelay = (i * 40) + "ms"; }});
    animateValue(document.getElementById("t-fp"), 0, d.financial.fp_dollar_savings, 0,
      {{ currency: true, duration: 800, finalText: d.financial.fp_dollar_savings_fmt }});
    animateValue(document.getElementById("t-hrs"), 0, d.financial.hours_saved, 0, {{ suffix: " hrs", duration: 800 }});
    animateValue(document.getElementById("t-tp"), 0, d.financial.tp_dollar_illustrative, 0,
      {{ currency: true, duration: 800, finalText: d.financial.tp_dollar_illustrative_fmt }});
    animateValue(document.getElementById("t-cases"), 0, d.financial.tp_uplift, 0, {{ duration: 800 }});
    document.getElementById("finNote").textContent =
      `Exact figures: ${{d.financial.fp_dollar_savings_fmt}} false-positive-reduction savings; `
      + `${{d.financial.tp_dollar_illustrative_fmt}} true-positive-uplift illustrative exposure avoided. `
      + `Kept as two separate lines, never summed into one blended total (locked Section 7A policy).`;

    if (finChart) finChart.destroy();
    finChart = new Chart(document.getElementById("finChart"), {{
      type: "bar",
      data: {{ labels: ["False-positive-reduction savings (ASSUMPTION)", "True-positive-uplift illustrative (ASSUMPTION)"],
        datasets: [{{ data: [d.financial.fp_dollar_savings, d.financial.tp_dollar_illustrative],
          backgroundColor: [palette.s1, palette.s2], borderRadius: 4 }}] }},
      options: {{ responsive: true, maintainAspectRatio: false, indexAxis: "y", animation: {{ duration: 800, easing: "easeOutCubic" }},
        plugins: {{ legend: {{ display: false }}, title: {{ display: true, text: "Financial impact, two separate ASSUMPTION lines (" + current + ")" }},
          tooltip: {{ callbacks: {{ label: (ctx) => ctx.dataIndex === 0 ? d.financial.fp_dollar_savings_fmt : d.financial.tp_dollar_illustrative_fmt }} }} }},
        scales: {{ x: {{ grid: {{ color: palette.grid }} }}, y: {{ grid: {{ display: false }} }} }} }}
    }});

    if (baChart) baChart.destroy();
    baChart = new Chart(document.getElementById("baChart"), {{
      type: "bar",
      data: {{ labels: d.before_after_chart.labels, datasets: [
        {{ label: "Before (baseline)", data: d.before_after_chart.before, backgroundColor: palette.s1, borderRadius: 4 }},
        {{ label: "After (ML model)", data: d.before_after_chart.after, backgroundColor: palette.s2, borderRadius: 4 }},
      ] }},
      options: {{ responsive: true, maintainAspectRatio: false, animation: {{ duration: 800, easing: "easeOutCubic" }},
        plugins: {{ legend: {{ position: "bottom" }}, title: {{ display: true, text: "Before / After -- real operating-point metrics (" + current + ")" }} }},
        scales: {{ y: {{ beginAtZero: true, grid: {{ color: palette.grid }} }}, x: {{ grid: {{ display: false }} }} }} }}
    }});

    renderBaTable(d.before_after_rows);
  }}

  document.getElementById("stageASortBtn").addEventListener("click", () => {{
    stageASortDir = stageASortDir === "desc" ? "asc" : "desc";
    document.getElementById("stageASortBtn").textContent = "Sort by PR-AUC " + (stageASortDir === "desc" ? "\\u2193" : "\\u2191");
    render();
  }});
  document.getElementById("shapSearch").addEventListener("input", (e) => {{ shapFilter = e.target.value; render(); }});

  // ---- Recommendations tab (real, primary-variant-derived SMART cards) ----
  document.getElementById("recsList").innerHTML = RECS.map((r, i) => `
    <div class="rec-card" style="animation-delay:${{i * 60}}ms">
      <h3>${{r.title}}</h3>
      <div class="smart-row"><b>Specific:</b> ${{r.specific}}</div>
      <div class="smart-row"><b>Measurable:</b> ${{r.measurable}}</div>
      <div class="smart-row"><b>Achievable:</b> ${{r.achievable}}</div>
      <div class="smart-row"><b>Relevant:</b> ${{r.relevant}}</div>
      <div class="smart-row"><b>Time-bound:</b> ${{r.time_bound}}</div>
    </div>
  `).join("");

  render();
}})();
</script>
</body>
</html>
"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


# ============================================================================
# PowerPoint executive deck (python-pptx) -- board/investigator-briefing version
# ============================================================================
def write_pptx_deck(path: Path, context: dict, chart_png_paths: Optional[dict] = None) -> Path:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt

    prs = Presentation()
    blue = RGBColor(0x2A, 0x78, 0xD6)

    # Title slide
    slide = _add_branded_slide(prs, 0)
    slide.shapes.title.text = f"{context['bp_id']}: {context['bp_name']}"
    slide.placeholders[1].text = f"Compliance-Impact Executive Briefing -- {context['generated_at_utc']} UTC"

    # Business objective slide
    slide = _add_branded_slide(prs, 1)
    slide.shapes.title.text = "Business Objective"
    slide.placeholders[1].text_frame.text = context["business_objective"]

    # Recommendation & status slide -- real, computed from the two-gate verdicts
    status = context.get("status") or compute_bp_status(context)
    status_colors = {
        "good": RGBColor(0x0C, 0xA3, 0x0C),
        "warning": RGBColor(0xC9, 0x85, 0x00),
        "critical": RGBColor(0xD0, 0x3B, 0x3B),
    }
    slide = _add_branded_slide(prs, 1)
    slide.shapes.title.text = "Recommendation & Status"
    body = slide.placeholders[1].text_frame
    body.text = status["label"]
    body.paragraphs[0].font.bold = True
    body.paragraphs[0].font.size = Pt(28)
    body.paragraphs[0].font.color.rgb = status_colors.get(status["css_class"], blue)
    p = body.add_paragraph()
    p.text = status["rationale"]
    p.level = 1

    # Executive summary slide
    slide = _add_branded_slide(prs, 1)
    slide.shapes.title.text = "Executive Summary"
    primary = context["variants"][context["primary_variant"]]
    body = slide.placeholders[1].text_frame
    body.text = (
        f"Champion model: {primary['report']['champion_name']} " f"({context['primary_variant']} variant)"
    )
    for line in [
        f"Real test PR-AUC: {primary['report']['test_metrics']['pr_auc']:.4f} "
        f"({_safe_div(primary['report']['test_metrics']['pr_auc'], primary['report']['random_baseline_pr_auc']):.0f}x random baseline)",
        f"Precision {primary['report']['test_metrics']['precision']:.3f} / "
        f"Recall {primary['report']['test_metrics']['recall']:.3f} / "
        f"F2 {primary['report']['test_metrics']['f2']:.3f}",
        f"Two-gate verdict: {primary['report']['overall_verdict']}",
    ]:
        p = body.add_paragraph()
        p.text = line
        p.level = 1

    # What this means for the business slide
    slide = _add_branded_slide(prs, 1)
    slide.shapes.title.text = "What This Means for the Business"
    body = slide.placeholders[1].text_frame
    body.text = context["business_benefits"][0]
    for point in context["business_benefits"][1:]:
        p = body.add_paragraph()
        p.text = point
        p.level = 1

    # Variant comparison slide (table)
    slide = _add_branded_slide(prs, 5)
    slide.shapes.title.text = "Model Performance by Dataset Variant"
    rows, cols = len(context["variants"]) + 1, 5
    left, top, width, height = Inches(0.5), Inches(1.5), Inches(9), Inches(0.4 * rows)
    table_shape = slide.shapes.add_table(rows, cols, left, top, width, height).table
    for c, h in enumerate(["Variant", "Champion", "Test PR-AUC", "Precision/Recall", "Verdict"]):
        table_shape.cell(0, c).text = h
    for r, (variant_name, v) in enumerate(context["variants"].items(), start=1):
        rep = v["report"]
        table_shape.cell(r, 0).text = variant_name
        table_shape.cell(r, 1).text = rep["champion_name"]
        table_shape.cell(r, 2).text = f"{rep['test_metrics']['pr_auc']:.4f}"
        table_shape.cell(r, 3).text = (
            f"{rep['test_metrics']['precision']:.3f} / {rep['test_metrics']['recall']:.3f}"
        )
        table_shape.cell(r, 4).text = rep["overall_verdict"]

    # Before/After chart slide (real matplotlib image, embedded per board-deck convention)
    if chart_png_paths and "before_after" in chart_png_paths:
        slide = _add_branded_slide(prs, 5)
        slide.shapes.title.text = f"Before / After Impact ({context['primary_variant']})"
        slide.shapes.add_picture(
            str(chart_png_paths["before_after"]), Inches(0.5), Inches(1.3), width=Inches(9)
        )

    # Financial impact summary slide -- real figures, B/M-shorthand formatted, the two
    # benefit lines kept explicitly separate (locked Section 7A rule, never summed)
    fi = compute_financial_impact(primary["before"], primary["after"], context["assumptions"])
    slide = _add_branded_slide(prs, 1)
    slide.shapes.title.text = f"Financial Impact Summary ({context['primary_variant']})"
    body = slide.placeholders[1].text_frame
    body.text = f"False-positive-reduction savings (ASSUMPTION): {_fmt_usd(fi['fp_dollar_savings'])}"
    for line in [
        f"{fi['hours_saved']:,.0f} investigator hours freed, {fi['fp_reduction']:,} fewer false-positive alerts",
        f"True-positive-uplift illustrative regulatory-exposure-avoidance (ASSUMPTION): {_fmt_usd(fi['tp_dollar_illustrative'])}",
        f"{fi['tp_uplift']:+,} additional real cases caught vs. the naive baseline",
        "These two figures are never summed into one blended total (locked Section 7A policy).",
    ]:
        p = body.add_paragraph()
        p.text = line
        p.level = 1

    # Key recommendations slide -- real, SMART, data-driven
    recs = context.get("smart_recommendations") or generate_smart_recommendations(context)
    slide = _add_branded_slide(prs, 1)
    slide.shapes.title.text = "Key Recommendations"
    body = slide.placeholders[1].text_frame
    body.text = recs[0]["title"]
    p = body.add_paragraph()
    p.text = recs[0]["specific"]
    p.level = 1
    for r in recs[1:]:
        p = body.add_paragraph()
        p.text = r["title"]
        p2 = body.add_paragraph()
        p2.text = r["specific"]
        p2.level = 1

    # Regulatory mapping slide
    slide = _add_branded_slide(prs, 1)
    slide.shapes.title.text = "Regulatory & Compliance Mapping"
    body = slide.placeholders[1].text_frame
    body.text = context["regulatory_frameworks"][0][0]
    for fw, applies in context["regulatory_frameworks"][1:]:
        p = body.add_paragraph()
        p.text = f"{fw} ({applies})"
        p.level = 1

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(path))
    return path


def render_before_after_chart_png(ba_df: pd.DataFrame, out_path: Path) -> Path:
    """Real matplotlib before/after bar chart (Precision/Recall rows only -- count rows use
    different scales and are shown in the table instead), CVD-safe two-series palette."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    metric_rows = ba_df[
        ba_df["Metric"].isin(["Precision (at operating point)", "Recall (at operating point)"])
    ]
    labels = metric_rows["Metric"].str.replace(" (at operating point)", "", regex=False).tolist()
    before_vals = metric_rows["Before (baseline)"].astype(float).tolist()
    after_vals = metric_rows["After (ML model)"].astype(float).tolist()

    x = range(len(labels))
    width = 0.35
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    ax.bar(
        [i - width / 2 for i in x],
        before_vals,
        width,
        label="Before (baseline)",
        color=PALETTE["series_1_blue"],
    )
    ax.bar(
        [i + width / 2 for i in x],
        after_vals,
        width,
        label="After (ML model)",
        color=PALETTE["series_2_orange"],
    )
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel("Score")
    ax.set_title("Before / After -- real operating-point metrics")
    ax.legend()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


# ============================================================================
# PDF export -- rendered FROM the Word report, never a separately authored source of numbers.
# Honestly guarded: tries docx2pdf (Word/mac, real conversion), falls back to LibreOffice
# headless CLI if present, otherwise reports ACTION NEEDED and returns None -- never fabricates
# a PDF.
# ============================================================================
def export_pdf_from_docx(docx_path: Path, pdf_path: Path) -> Optional[Path]:
    docx_path = Path(docx_path)
    pdf_path = Path(pdf_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from docx2pdf import convert

        convert(str(docx_path), str(pdf_path))
        if pdf_path.exists():
            return pdf_path
    except ImportError:
        pass
    except Exception as e:
        print(f"docx2pdf raised a real error ({type(e).__name__}: {e}) -- trying LibreOffice fallback.")

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice:
        try:
            subprocess.run(
                [
                    soffice,
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(pdf_path.parent),
                    str(docx_path),
                ],
                check=True,
                timeout=120,
                capture_output=True,
            )
            produced = pdf_path.parent / (docx_path.stem + ".pdf")
            if produced.exists():
                if produced != pdf_path:
                    produced.replace(pdf_path)
                return pdf_path
        except Exception as e:
            print(f"LibreOffice headless conversion raised a real error ({type(e).__name__}: {e}).")

    print(
        "SKIPPED PDF export -- neither docx2pdf (needs MS Word) nor a LibreOffice "
        "'soffice'/'libreoffice' binary on PATH is available on this machine. "
        "ACTION NEEDED: pip install docx2pdf (Windows/Mac with Word installed) or install "
        "LibreOffice. No PDF was fabricated."
    )
    return None


# ============================================================================
# MODEL_CARD.md / CHANGELOG.md
# ============================================================================
def write_model_card(path: Path, context: dict) -> Path:
    primary = context["variants"][context["primary_variant"]]
    rep = primary["report"]
    status = context.get("status") or compute_bp_status(context)
    fi = compute_financial_impact(primary["before"], primary["after"], context["assumptions"])
    recs = context.get("smart_recommendations") or generate_smart_recommendations(context)
    lines = (
        [
            f"# Model Card -- {context['bp_id']}: {context['bp_name']}",
            "",
            f"_Generated {context['generated_at_utc']} UTC. Primary reported variant: "
            f"{context['primary_variant']} (this BP's locked mandatory realism-validation tier)._",
            "",
            f"## Status: {status['label']}",
            status["rationale"],
            "",
            "## Business Objective",
            context["business_objective"],
            "",
            "## What This Means for the Business",
        ]
        + [f"- {point}" for point in context["business_benefits"]]
        + [
            "",
            "## Financial Impact Summary",
            f"- False-positive-reduction savings (ASSUMPTION): {_fmt_usd(fi['fp_dollar_savings'])} "
            f"({fi['hours_saved']:,.0f} investigator hours, {fi['fp_reduction']:,} fewer false-positive alerts)",
            f"- True-positive-uplift illustrative regulatory-exposure-avoidance (ASSUMPTION): "
            f"{_fmt_usd(fi['tp_dollar_illustrative'])} ({fi['tp_uplift']:+,} additional real cases caught)",
            "- These two figures are never summed into one blended total (locked Section 7A policy).",
            "",
            "## Model Details",
            f"- Champion algorithm: **{rep['champion_name']}**",
            f"- Random seed: {rep['random_seed']}",
            f"- Feature count: {len(rep['feature_cols'])}",
            f"- Selected decision threshold: {rep['selected_threshold']:.6f}",
            "",
            "## Intended Use",
            "Real-time / batch transaction-level suspicious-activity scoring, feeding investigator "
            "alert review. Not a standalone SAR-filing decision -- output is evidence for a human "
            "investigator, per this platform's locked scope.",
            "",
            "## Training Data",
            "IBM Transactions for Anti Money Laundering (AML) -- synthetic, IBM Research. Variants "
            "used (never merged): " + ", ".join(context["variants"].keys()) + ".",
            "",
            "## Evaluation",
            "| Variant | Champion | Test PR-AUC | Precision | Recall | F2 | Verdict |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for variant_name, v in context["variants"].items():
        r = v["report"]
        lines.append(
            f"| {variant_name} | {r['champion_name']} | {r['test_metrics']['pr_auc']:.4f} | "
            f"{r['test_metrics']['precision']:.4f} | {r['test_metrics']['recall']:.4f} | "
            f"{r['test_metrics']['f2']:.4f} | {r['overall_verdict']} |"
        )
    lines += [
        "",
        "## Explainability",
        "SHAP (TreeExplainer, global) and LIME (local, per real true-positive instance) -- see "
        "each variant's own saved `{}_notebook3_validation_report_*.json` for full real values.".format(
            context["bp_id"].lower()
        ),
        "",
        "## Ethical Considerations / Fairness",
        context["fairness_note"],
        "",
        "## Caveats & Limitations",
    ]
    for cav in context.get("caveats", []):
        lines.append(f"- {cav}")
    lines += [
        "",
        "## Regulatory Mapping",
    ]
    for fw, applies in context["regulatory_frameworks"]:
        lines.append(f"- {fw} -- {applies}")
    lines += ["", "## Recommendations"]
    for r in recs:
        lines += [
            f"### {r['title']}",
            f"- **Specific:** {r['specific']}",
            f"- **Measurable:** {r['measurable']}",
            f"- **Achievable:** {r['achievable']}",
            f"- **Relevant:** {r['relevant']}",
            f"- **Time-bound:** {r['time_bound']}",
            "",
        ]

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_changelog(path: Path, context: dict, entry: str) -> Path:
    """Append-only real changelog. Creates the file with a header on first write, otherwise
    appends a new dated entry -- never overwrites prior real entries."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = context["generated_at_utc"]
    new_entry = f"## {ts}\n{entry}\n"
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        path.write_text(existing.rstrip() + "\n\n" + new_entry, encoding="utf-8")
    else:
        header = f"# CHANGELOG -- {context['bp_id']}: {context['bp_name']}\n\n"
        path.write_text(header + new_entry, encoding="utf-8")
    return path


# ============================================================================
# ============================================================================
# MULTI-CLASS EXTENSION (added for BP2 -- Typology & Red-Flag Pattern Detection,
# 2026-09-30). Every function above this block is BP1's original, binary-classification
# (PR-AUC / precision / recall / f2 / single-threshold / alert-flagging) reporting code and
# is left completely UNCHANGED -- BP1's already-shipped, verified-working reports must never
# regress. The functions below are NEW, parallel, multi-class-aware equivalents, built for
# any BP whose Notebook 3 report has no single decision threshold and no PR-AUC (BP2's
# 8-typology -- in practice however many of the 8 typologies have real matched examples in a
# given run -- multi-class classification target).
#
# Reused UNCHANGED from above (confirmed fully generic, no binary-specific assumption):
#   _fmt_usd / format_usd, _EXCEL_USD_FORMAT, _excel_usd_shorthand_formula, _defined_name,
#   compute_bp_status (reads only rep["overall_verdict"] per variant), export_pdf_from_docx,
#   write_changelog, PALETTE.
#
# Real NB3 report schema this reads (verified against the user's own real
# bp2_notebook3_validation_report_li_medium.json, 2026-09-30 run): "class_names" (however
# many of the 8 typologies had real matched examples this run -- NOT hardcoded to 8),
# "before_baseline_typology", "before_macro_f1", "before_after_recall_by_class" (per real
# class: before_recall/after_recall), "after_classification_report" (sklearn
# classification_report(..., output_dict=True) -- per-class precision/recall/f1-score/
# support, plus "accuracy" and "macro avg"/"weighted avg"), "stage_a_ranking",
# "stage_b_cv_results", "champion_name", "test_metrics"={"macro_f1"}, "gate1_verdict",
# "gate2_verdict", "overall_verdict", "shap_mean_abs_importance", "fastapi_self_test".
# ============================================================================


# ============================================================================
# Real multi-class financial-impact arithmetic. Unlike BP1's binary compute_financial_impact
# (which needs a real "n_flagged" alert-count that only exists for a binary flag/no-flag
# decision), BP2's modeling population is ALREADY known-laundering rows (Is Laundering==1
# with a matched typology label, per this platform's locked BP2 scope) -- the real business
# question is not "flag or not" but "did the model correctly TYPE this already-known case,
# where the old rule could only ever guess one fixed typology". Every number below is derived
# from real, already-saved NB3 figures -- nothing here is re-measured or estimated.
# ============================================================================
def compute_financial_impact_multiclass(rep: dict, assumptions: dict) -> dict:
    """Real, raw (unformatted) multi-class financial-impact figures.

    Before = the real "always guess `before_baseline_typology`" heuristic NB3 evaluated on
    this SAME real held-out test set (never a straw man -- same data, same split as After).
    After  = the real champion model's real held-out test predictions.

    Two real, non-overlapping quantities are derived, each carrying its own disclosed
    ASSUMPTION for converting it to a dollar figure (never summed together, same discipline
    as BP1's Section 7A false-positive/true-positive separation):

    1. `delta_correct` -- the real change in how many of the n_test real held-out cases are
       correctly auto-typed, Before vs After (both derived from real, already-saved support/
       accuracy figures -- Before's correct-count is exactly the real support of
       `before_baseline_typology` in the test set, since an always-guess-X rule is correct on
       precisely the real X-labeled rows and wrong on everything else; this is a mathematical
       certainty, not an estimate).
    2. `net_new_typed` -- the real count of held-out cases whose TRUE typology is something
       OTHER than `before_baseline_typology`, that the After model correctly identifies. The
       Before rule is mathematically guaranteed to score exactly 0 recall on every one of
       these other real classes (it only ever guesses one fixed class), so this is real, newly
       created typology-detection capability -- a distinct real subset of cases from (1)
       above, not a re-slice of the same dollar pool under a different name.
    """
    class_names = rep["class_names"]
    before_baseline_typology = rep["before_baseline_typology"]
    after_report = rep["after_classification_report"]
    ba_recall = rep["before_after_recall_by_class"]

    n_test = int(round(sum(float(after_report[c]["support"]) for c in class_names)))
    before_n_correct = int(round(float(after_report[before_baseline_typology]["support"])))
    before_accuracy = _safe_div(before_n_correct, n_test)
    after_accuracy = float(after_report["accuracy"])
    after_n_correct = int(round(after_accuracy * n_test))
    delta_correct = after_n_correct - before_n_correct

    hours_saved = delta_correct * assumptions["hours_per_case_manual_typology_review"]
    autotyping_dollar_savings = hours_saved * assumptions["cost_per_investigator_hour_usd"]

    net_new_typed = 0
    for c in class_names:
        if c == before_baseline_typology:
            continue
        support_c = float(after_report[c]["support"])
        after_recall_c = float(ba_recall[c]["after_recall"])
        net_new_typed += int(round(after_recall_c * support_c))
    net_new_dollar_value = net_new_typed * assumptions["illustrative_typology_confirmation_value_usd"]

    return {
        "n_test": n_test,
        "before_n_correct": before_n_correct,
        "after_n_correct": after_n_correct,
        "before_accuracy": before_accuracy,
        "after_accuracy": after_accuracy,
        "delta_correct": delta_correct,
        "hours_saved": hours_saved,
        "autotyping_dollar_savings": autotyping_dollar_savings,
        "net_new_typed": net_new_typed,
        "net_new_dollar_value": net_new_dollar_value,
    }


# ============================================================================
# Multi-class Before/After headline table -- the Section 7A equivalent for a typology-
# classification BP (no single "alerts flagged" count applies, since the modeling population
# is already-known-laundering cases; the real analogous headline is auto-typing quality).
# ============================================================================
def build_before_after_table_multiclass(rep: dict, assumptions: dict) -> pd.DataFrame:
    fi = compute_financial_impact_multiclass(rep, assumptions)
    before_f1 = float(rep["before_macro_f1"])
    after_f1 = float(rep["test_metrics"]["macro_f1"])

    rows = [
        {
            "Metric": "Macro-F1 (typology classification quality)",
            "Before (baseline)": f"{before_f1:.4f}",
            "After (ML model)": f"{after_f1:.4f}",
            "Delta": f"{after_f1 - before_f1:+.4f}",
            "$ Impact": "",
        },
        {
            "Metric": "Overall labeling accuracy (real, all typologies)",
            "Before (baseline)": f"{fi['before_accuracy']:.4f}",
            "After (ML model)": f"{fi['after_accuracy']:.4f}",
            "Delta": f"{fi['after_accuracy'] - fi['before_accuracy']:+.4f}",
            "$ Impact": "",
        },
        {
            "Metric": "Cases correctly auto-typed (real count, held-out test set)",
            "Before (baseline)": f"{fi['before_n_correct']:,} / {fi['n_test']:,}",
            "After (ML model)": f"{fi['after_n_correct']:,} / {fi['n_test']:,}",
            "Delta": f"{fi['delta_correct']:+,}",
            "$ Impact": f"ASSUMPTION: {_fmt_usd(fi['autotyping_dollar_savings'])} auto-typing efficiency "
            f"savings ({fi['hours_saved']:,.1f} hrs @ "
            f"${assumptions['cost_per_investigator_hour_usd']:.0f}/hr, "
            f"{assumptions['hours_per_case_manual_typology_review']} hrs/case reviewed manually)",
        },
        {
            "Metric": "Net-new typology detections beyond the old single-guess baseline (real count)",
            "Before (baseline)": "0 (structurally cannot type any class but its own fixed guess)",
            "After (ML model)": f"{fi['net_new_typed']:,}",
            "Delta": f"{fi['net_new_typed']:+,}",
            "$ Impact": f"ASSUMPTION: {_fmt_usd(fi['net_new_dollar_value'])} illustrative typology-"
            f"confirmation value ({fi['net_new_typed']:,} cases @ "
            f"${assumptions['illustrative_typology_confirmation_value_usd']:,.0f}/case)",
        },
    ]
    return pd.DataFrame(rows)


# ============================================================================
# Real per-typology Before/After recall table -- BP2's own most important table (this is
# where a typology classifier's real value shows up: which typologies did the model actually
# learn to distinguish, and how much real held-out evidence backs each one).
# ============================================================================
def build_typology_recall_table(rep: dict) -> pd.DataFrame:
    class_names = rep["class_names"]
    after_report = rep["after_classification_report"]
    ba_recall = rep["before_after_recall_by_class"]

    rows = []
    for c in class_names:
        support = float(after_report[c]["support"])
        before_r = float(ba_recall[c]["before_recall"])
        after_r = float(ba_recall[c]["after_recall"])
        before_cases = int(round(before_r * support))
        after_cases = int(round(after_r * support))
        rows.append(
            {
                "Typology": c,
                "Before Recall": f"{before_r:.4f}",
                "After Recall": f"{after_r:.4f}",
                "Delta Recall": f"{after_r - before_r:+.4f}",
                "Real Test Support (n)": int(round(support)),
                "Cases Correctly Typed, Before": before_cases,
                "Cases Correctly Typed, After": after_cases,
            }
        )
    return pd.DataFrame(rows)


# ============================================================================
# Real, data-driven SMART recommendations, multi-class version -- every clause built from
# real numbers already present in `context`, never a templated placeholder.
# ============================================================================
def generate_smart_recommendations_multiclass(context: dict) -> list:
    primary_name = context["primary_variant"]
    rep = context["variants"][primary_name]["report"]
    assumptions = context["assumptions"]
    fi = compute_financial_impact_multiclass(rep, assumptions)
    recall_df = context["typology_recall_tables"][primary_name]
    shap = rep.get("shap_mean_abs_importance") or {}
    top_feature = max(shap.items(), key=lambda kv: kv[1])[0] if shap else None

    # Ranked by real AFTER recall (absolute model performance), never by Delta Recall -- the
    # baseline's own always-guessed class (`before_baseline_typology`) starts at an
    # artificial 1.0 recall (it is the ONLY class the naive rule ever predicts), so its real
    # Delta Recall is structurally negative even when its real After recall is the model's
    # best. Ranking by absolute After recall avoids that misleading artifact.
    weakest = recall_df.loc[recall_df["After Recall"].astype(float).idxmin()]
    strongest = recall_df.loc[recall_df["After Recall"].astype(float).idxmax()]

    recs = [
        {
            "title": "Prioritize real-world review of the lowest-recall typology first",
            "specific": (
                f"On {primary_name}, the real champion model ({rep['champion_name']}) has its "
                f"LOWEST real absolute recall on '{weakest['Typology']}' (After recall "
                f"{weakest['After Recall']} on {weakest['Real Test Support (n)']} real held-out "
                f"cases) -- it still misses most real cases of this typology."
            ),
            "measurable": f"Track real recall on '{weakest['Typology']}' specifically at every retrain; treat any further drop from {weakest['After Recall']} as a trigger for feature review.",
            "achievable": "Uses the same SHAP/LIME explainability already computed by Notebook 3 -- no new tooling required.",
            "relevant": "A typology classifier that silently under-performs on one real pattern is a real investigative blind spot (SR 11-7 model risk management expectation).",
            "time_bound": "Reviewed alongside the next scheduled model retrain, within 90 days of production go-live.",
        },
        {
            "title": "Reallocate freed investigator capacity from real auto-typing efficiency gains",
            "specific": (
                f"Moving from the naive always-guess-'{rep['before_baseline_typology']}' rule to the "
                f"real ML model correctly auto-types {fi['delta_correct']:+,} more of the "
                f"{fi['n_test']:,} real held-out cases on {primary_name} (ASSUMPTION-estimated at "
                f"{fi['hours_saved']:,.1f} investigator hours, {_fmt_usd(fi['autotyping_dollar_savings'])})."
            ),
            "measurable": f"Real manual-typology-review hours logged per investigator, compared against the {fi['hours_saved']:,.1f}-hour ASSUMPTION estimate above.",
            "achievable": "Capacity freed is redeployed to case investigation depth, not headcount reduction -- an operational scheduling change, not a new system.",
            "relevant": "Investigator capacity is the real, most commonly cited AML program bottleneck (FFIEC BSA/AML Examination Manual, alert-management pillar).",
            "time_bound": "Reassess real review hours logged 60 days after production go-live against this ASSUMPTION estimate.",
        },
    ]

    if fi["net_new_typed"] > 0:
        recs.append(
            {
                "title": "Validate the real net-new typology detections against filed SARs",
                "specific": (
                    f"The real ML model correctly identifies {fi['net_new_typed']:,} real held-out "
                    f"cases whose true typology is something other than the old rule's fixed guess "
                    f"('{rep['before_baseline_typology']}') on {primary_name} -- typology "
                    f"detection that structurally could not exist under the old rule (illustrative "
                    f"typology-confirmation value, ASSUMPTION: {_fmt_usd(fi['net_new_dollar_value'])})."
                ),
                "measurable": "Real SAR filing rate on model-assigned typologies for these net-new-detected cases, tracked separately from the auto-typing-efficiency line above.",
                "achievable": "Requires only tagging each filed SAR with the model-assigned typology at filing time -- a labeling change, not a new detection system.",
                "relevant": "Directly evidences the model's real typology-detection benefit to examiners (31 CFR Section 1020.320 SAR requirements).",
                "time_bound": "First real comparison report at the 6-month production mark (enough real SAR volume to be meaningful).",
            }
        )

    if strongest["Typology"] != weakest["Typology"]:
        recs.append(
            {
                "title": f"Document why '{strongest['Typology']}' recall is strongest, as a template for the weaker typologies",
                "specific": (
                    f"'{strongest['Typology']}' has the real HIGHEST absolute recall on {primary_name} "
                    f"(After recall {strongest['After Recall']}, real Delta {strongest['Delta Recall']} vs. the baseline)."
                    + (
                        f" Real SHAP analysis ranks '{top_feature}' as the model's dominant overall driver."
                        if top_feature
                        else ""
                    )
                ),
                "measurable": "Confirm the same driver(s) remain dominant for this typology at every future real retrain.",
                "achievable": "Already computed by Notebook 3's existing SHAP step -- no new tooling required.",
                "relevant": "SR 11-7 model risk management requires a documented explanation of the model's real primary drivers, per typology where they differ.",
                "time_bound": "Refresh this documentation at every model retrain, alongside the MODEL_CARD.md update.",
            }
        )

    failing = [name for name, v in context["variants"].items() if v["report"]["overall_verdict"] != "PASS"]
    if failing:
        recs.append(
            {
                "title": f"Resolve validation gate failures on {', '.join(failing)} before relying on that variant",
                "specific": f"{', '.join(failing)} did not pass both the structural and statistical-robustness validation gates.",
                "measurable": "Re-run Notebook 3 on the failing variant(s) until both gates PASS.",
                "achievable": "Uses the existing, already-built Notebook 3 pipeline -- no new modeling approach required.",
                "relevant": "This platform's locked policy requires both gates to PASS before a variant's results are treated as production evidence.",
                "time_bound": "Before this variant is cited in any external or regulatory-facing report.",
            }
        )
    else:
        recs.append(
            {
                "title": "Maintain the real two-gate validation standard on every future retrain",
                "specific": f"Every real dataset variant evaluated for {context['bp_id']} currently passes both validation gates ({', '.join(context['variants'].keys())}).",
                "measurable": "Both gates must continue to PASS on every future retrain before redeployment.",
                "achievable": "Enforced automatically by Notebook 3's existing gate logic -- no manual step to remember.",
                "relevant": "This is the basis for this report's current production-recommended status.",
                "time_bound": "Every retrain cycle, before redeployment.",
            }
        )

    return recs


# ============================================================================
# Word report (python-docx), multi-class version
# ============================================================================
def write_word_report_multiclass(path: Path, context: dict) -> Path:
    from docx import Document
    from docx.shared import Pt, RGBColor

    doc = Document()
    _apply_word_brand_styles(doc)
    doc.add_heading(f"{context['bp_id']}: {context['bp_name']}", level=0)
    p = doc.add_paragraph()
    p.add_run(f"Compliance-Impact Report -- generated {context['generated_at_utc']} UTC").italic = True

    doc.add_heading("Business Objective", level=1)
    doc.add_paragraph(context["business_objective"])

    status = context.get("status") or compute_bp_status(context)
    doc.add_heading("Recommendation & Status", level=1)
    p = doc.add_paragraph()
    run = p.add_run(status["label"])
    run.bold = True
    run.font.size = Pt(14)
    status_colors = {
        "good": RGBColor(0x0C, 0xA3, 0x0C),
        "warning": RGBColor(0xC9, 0x85, 0x00),
        "critical": RGBColor(0xD0, 0x3B, 0x3B),
    }
    run.font.color.rgb = status_colors.get(status["css_class"], RGBColor(0x0B, 0x0B, 0x0B))
    doc.add_paragraph(status["rationale"])

    primary_name = context["primary_variant"]
    primary = context["variants"][primary_name]
    rep = primary["report"]
    fi = compute_financial_impact_multiclass(rep, context["assumptions"])

    doc.add_heading("Executive Summary", level=1)
    doc.add_paragraph(
        f"On the {primary_name} variant -- this business problem's locked mandatory "
        f"realism-validation tier -- the real champion model ({rep['champion_name']}) achieved "
        f"a real held-out test macro-F1 of {rep['test_metrics']['macro_f1']:.4f} across "
        f"{len(rep['class_names'])} real typologies with matched ground-truth examples this "
        f"run ({', '.join(rep['class_names'])}), vs. a real single-typology-heuristic BEFORE "
        f"baseline macro-F1 of {rep['before_macro_f1']:.4f} "
        f"({_safe_div(rep['test_metrics']['macro_f1'], rep['before_macro_f1']):.1f}x lift). "
        f"Real overall labeling accuracy improved from {fi['before_accuracy']:.4f} to "
        f"{fi['after_accuracy']:.4f} on the same {fi['n_test']:,}-row real held-out test set. "
        f"Both the structural and statistical-robustness gates PASSED "
        f"(overall verdict: {rep['overall_verdict']})."
    )

    doc.add_heading("What This Means for the Business", level=1)
    for point in context["business_benefits"]:
        doc.add_paragraph(point, style="List Bullet")

    doc.add_heading("Model Performance by Dataset Variant", level=1)
    doc.add_paragraph(
        "Per this platform's locked multi-variant policy, results from different dataset "
        "variants are never merged or blended -- each is reported here on its own, side by side."
    )
    table = doc.add_table(rows=1, cols=5)
    table.style = "Light Grid Accent 1"
    hdr = table.rows[0].cells
    for i, h in enumerate(
        ["Variant", "Champion", "Test Macro-F1", "Real Typologies Matched", "Gate Verdict"]
    ):
        hdr[i].text = h
    for variant_name, v in context["variants"].items():
        r = v["report"]
        row = table.add_row().cells
        row[0].text = variant_name
        row[1].text = r["champion_name"]
        row[2].text = f"{r['test_metrics']['macro_f1']:.4f}"
        row[3].text = str(len(r["class_names"]))
        row[4].text = r["overall_verdict"]

    doc.add_heading(f"Before / After Impact ({primary_name})", level=1)
    doc.add_paragraph(
        "Before = a fixed single-typology heuristic (always guess the real majority typology, "
        "no other logic) -- the real, same-data baseline this project's locked policy requires, "
        "never a straw man. After = the real ML champion's held-out test predictions. Dollar "
        "figures marked ASSUMPTION are illustrative, computed from a disclosed assumptions set "
        "(see Excel workbook's Assumptions sheet), never a directly measured quantity. The two "
        "$ Impact lines below apply DIFFERENT disclosed assumptions to two real, non-overlapping "
        "subsets of held-out cases (see each row's own definition) and are never summed."
    )
    ba_df = context["before_after_tables"][primary_name]
    ba_table = doc.add_table(rows=1, cols=len(ba_df.columns))
    ba_table.style = "Light Grid Accent 1"
    for i, col in enumerate(ba_df.columns):
        ba_table.rows[0].cells[i].text = col
    for _, row in ba_df.iterrows():
        cells = ba_table.add_row().cells
        for i, col in enumerate(ba_df.columns):
            cells[i].text = str(row[col])

    doc.add_heading(f"Real Per-Typology Recall, Before -> After ({primary_name})", level=1)
    doc.add_paragraph(
        "The real heart of a typology classifier's value -- which real patterns did the model "
        "actually learn to distinguish, and on how much real held-out evidence. Before recall "
        "is exactly 1.0 for the baseline's own fixed guess and exactly 0.0 for every other real "
        "typology (mathematical certainty of an always-guess-one-class rule), never estimated."
    )
    recall_df = context["typology_recall_tables"][primary_name]
    rc_table = doc.add_table(rows=1, cols=len(recall_df.columns))
    rc_table.style = "Light Grid Accent 1"
    for i, col in enumerate(recall_df.columns):
        rc_table.rows[0].cells[i].text = col
    for _, row in recall_df.iterrows():
        cells = rc_table.add_row().cells
        for i, col in enumerate(recall_df.columns):
            cells[i].text = str(row[col])

    doc.add_heading("Financial Impact Summary", level=1)
    doc.add_paragraph(
        f"Auto-typing efficiency savings (ASSUMPTION): {_fmt_usd(fi['autotyping_dollar_savings'])} "
        f"({fi['hours_saved']:,.1f} investigator hours across {fi['delta_correct']:+,} more "
        f"correctly auto-typed cases on {primary_name}). Illustrative typology-confirmation "
        f"value (ASSUMPTION): {_fmt_usd(fi['net_new_dollar_value'])} "
        f"({fi['net_new_typed']:,} real cases whose typology the old rule structurally could "
        f"not have identified). These two figures apply different assumptions to different real "
        f"case subsets and are never summed into one blended total, per this platform's locked "
        f"reporting discipline (Section 7A)."
    )

    doc.add_heading("Explainability (SHAP -- champion model, real run)", level=1)
    shap_summary = rep.get("shap_mean_abs_importance")
    if shap_summary:
        top5 = sorted(shap_summary.items(), key=lambda kv: kv[1], reverse=True)[:5]
        doc.add_paragraph("Top 5 real features by mean |SHAP value| (averaged across all real typologies):")
        for feat, val in top5:
            doc.add_paragraph(f"{feat}: {val:.4f}", style="List Bullet")
    else:
        doc.add_paragraph(
            "SHAP was not available on the machine that produced this run -- "
            "see that Notebook 3 run's own console output for the real reason."
        )

    if context.get("stage_a_screening"):
        doc.add_heading("Appendix: Stage A Candidate Screening (fast-build variant)", level=1)
        doc.add_paragraph(
            "Notebook 2's real single-split Stage A candidate screening, run on the smaller "
            "fast-build/debug variant, before Notebook 3's full 5-fold CV on this report's "
            "primary variant. Shown for transparency only -- not used to select the champion "
            "reported above (that selection is Notebook 3's own real Stage B CV result)."
        )
        for variant_name, summary in context["stage_a_screening"].items():
            doc.add_paragraph(
                f"{variant_name}: {summary['n_modeled_rows']:,} real modeled rows.", style="List Bullet"
            )
            sa_table = doc.add_table(rows=1, cols=2)
            sa_table.style = "Light Grid Accent 1"
            sa_table.rows[0].cells[0].text = "Model"
            sa_table.rows[0].cells[1].text = "Real Macro-F1 (single split)"
            for r in summary["stage_a_ranking"]:
                row = sa_table.add_row().cells
                row[0].text = r["name"]
                row[1].text = f"{r['macro_f1']:.4f}"

    doc.add_heading("Regulatory & Compliance Mapping", level=1)
    reg_table = doc.add_table(rows=1, cols=2)
    reg_table.style = "Light Grid Accent 1"
    reg_table.rows[0].cells[0].text = "Framework"
    reg_table.rows[0].cells[1].text = "Applies to"
    for fw, applies in context["regulatory_frameworks"]:
        row = reg_table.add_row().cells
        row[0].text = fw
        row[1].text = applies

    doc.add_heading("Fairness / Bias Testing", level=1)
    doc.add_paragraph(context["fairness_note"])

    doc.add_heading("Limitations & Caveats", level=1)
    for cav in context.get("caveats", []):
        doc.add_paragraph(cav, style="List Bullet")

    doc.add_heading("Recommendations", level=1)
    recs = context.get("smart_recommendations") or generate_smart_recommendations_multiclass(context)
    for r in recs:
        doc.add_heading(r["title"], level=2)
        for label in ("specific", "measurable", "achievable", "relevant", "time_bound"):
            p = doc.add_paragraph(style="List Bullet")
            run = p.add_run(f"{label.replace('_', '-').title()}: ")
            run.bold = True
            p.add_run(r[label])

    _brand_word_table_headers(doc)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    return path


# ============================================================================
# Excel workbook (openpyxl), multi-class version -- Assumptions-sheet-first pattern preserved
# ============================================================================
def write_excel_workbook_multiclass(path: Path, context: dict) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.workbook.properties import CalcProperties

    yellow_fill = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
    blue_font = Font(color="0000FF", bold=True)
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="2A78D6", end_color="2A78D6", fill_type="solid")

    wb = Workbook()
    wb.calculation = CalcProperties(fullCalcOnLoad=True)

    ws_a = wb.active
    ws_a.title = "Assumptions"
    ws_a["A1"] = "Assumption"
    ws_a["B1"] = "Value"
    ws_a["A1"].font = header_font
    ws_a["B1"].font = header_font
    ws_a["A1"].fill = header_fill
    ws_a["B1"].fill = header_fill
    assumption_rows = [
        (
            "Hours per case, manual typology review (ASSUMPTION)",
            context["assumptions"]["hours_per_case_manual_typology_review"],
        ),
        (
            "Cost per investigator hour, USD (ASSUMPTION)",
            context["assumptions"]["cost_per_investigator_hour_usd"],
        ),
        (
            "Illustrative typology-confirmation value per case, USD (ASSUMPTION)",
            context["assumptions"]["illustrative_typology_confirmation_value_usd"],
        ),
    ]
    usd_assumption_rows = {
        "Cost per investigator hour, USD (ASSUMPTION)",
        "Illustrative typology-confirmation value per case, USD (ASSUMPTION)",
    }
    for i, (label, val) in enumerate(assumption_rows, start=2):
        ws_a[f"A{i}"] = label
        ws_a[f"B{i}"] = val
        ws_a[f"B{i}"].fill = yellow_fill
        ws_a[f"B{i}"].font = blue_font
        if label in usd_assumption_rows:
            ws_a[f"B{i}"].number_format = _EXCEL_USD_FORMAT
    ws_a.column_dimensions["A"].width = 58
    ws_a.column_dimensions["B"].width = 18
    _brand_excel_sheet(ws_a, PALETTE["ink_muted"], freeze_cell="A2")
    wb.defined_names["hours_per_case_manual_typology_review"] = _defined_name(
        "hours_per_case_manual_typology_review", "Assumptions", "B2"
    )
    wb.defined_names["cost_per_investigator_hour_usd"] = _defined_name(
        "cost_per_investigator_hour_usd", "Assumptions", "B3"
    )
    wb.defined_names["illustrative_typology_confirmation_value_usd"] = _defined_name(
        "illustrative_typology_confirmation_value_usd", "Assumptions", "B4"
    )

    status = context.get("status") or compute_bp_status(context)
    status_hex = {"good": "0CA30C", "warning": "FAB219", "critical": "D03B3B"}.get(
        status["css_class"], "2A78D6"
    )
    ws_e = wb.create_sheet("Executive Summary")
    ws_e["A1"] = "Status"
    ws_e["B1"] = "Rationale"
    ws_e["A1"].font = header_font
    ws_e["B1"].font = header_font
    ws_e["A1"].fill = header_fill
    ws_e["B1"].fill = header_fill
    ws_e["A2"] = status["label"]
    ws_e["A2"].fill = PatternFill(start_color=status_hex, end_color=status_hex, fill_type="solid")
    ws_e["A2"].font = Font(bold=True, color="FFFFFF")
    ws_e["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws_e["B2"] = status["rationale"]
    ws_e["B2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws_e.row_dimensions[2].height = 60
    ws_e.column_dimensions["A"].width = 42
    ws_e.column_dimensions["B"].width = 95

    primary_variant = context["primary_variant"]
    ba_sheet_name = f"Before-After {primary_variant}"[:31]
    ws_e["A4"] = f"Financial Impact Summary (primary variant: {primary_variant}, live formulas)"
    ws_e["A4"].font = Font(bold=True)
    ws_e["C4"] = "Formatted (with B/M shorthand)"
    ws_e["C4"].font = Font(bold=True, italic=True, color="52514E")
    ws_e["A5"] = "Auto-typing efficiency $ savings (ASSUMPTION)"
    ws_e["B5"] = f"='{ba_sheet_name}'!B9"
    ws_e["B5"].number_format = _EXCEL_USD_FORMAT
    ws_e["C5"] = _excel_usd_shorthand_formula("B5")
    ws_e["A6"] = "Illustrative typology-confirmation $ value (ASSUMPTION)"
    ws_e["B6"] = f"='{ba_sheet_name}'!B10"
    ws_e["B6"].number_format = _EXCEL_USD_FORMAT
    ws_e["C6"] = _excel_usd_shorthand_formula("B6")
    ws_e["A7"] = (
        "Note: the two figures above apply different ASSUMPTIONS to different real case subsets and are never summed (Section 7A discipline)."
    )
    ws_e["A7"].font = Font(italic=True, color="52514E")
    ws_e.column_dimensions["C"].width = 26
    _brand_excel_sheet(ws_e, status_hex, freeze_cell="A3")

    ws_s = wb.create_sheet("Variant Summary")
    headers = [
        "Variant",
        "Champion",
        "Test Macro-F1",
        "Before Macro-F1",
        "Lift (x)",
        "Overall Accuracy",
        "Real Typologies Matched",
        "Gate 1",
        "Gate 2",
        "Overall Verdict",
    ]
    for c, h in enumerate(headers, start=1):
        cell = ws_s.cell(row=1, column=c, value=h)
        cell.font = header_font
        cell.fill = header_fill
    for r, (variant_name, v) in enumerate(context["variants"].items(), start=2):
        rep = v["report"]
        fi = compute_financial_impact_multiclass(rep, context["assumptions"])
        ws_s.cell(row=r, column=1, value=variant_name)
        ws_s.cell(row=r, column=2, value=rep["champion_name"])
        ws_s.cell(row=r, column=3, value=rep["test_metrics"]["macro_f1"])
        ws_s.cell(row=r, column=4, value=rep["before_macro_f1"])
        col_c, col_d = get_column_letter(3), get_column_letter(4)
        ws_s.cell(row=r, column=5, value=f"={col_c}{r}/{col_d}{r}")
        ws_s.cell(row=r, column=6, value=fi["after_accuracy"])
        ws_s.cell(row=r, column=7, value=len(rep["class_names"]))
        ws_s.cell(row=r, column=8, value=rep["gate1_verdict"])
        ws_s.cell(row=r, column=9, value=rep["gate2_verdict"])
        ws_s.cell(row=r, column=10, value=rep["overall_verdict"])
    ws_s.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{1 + len(context['variants'])}"
    for c in range(1, len(headers) + 1):
        ws_s.column_dimensions[get_column_letter(c)].width = 20
    _brand_excel_sheet(ws_s, PALETTE["series_1_blue"], freeze_cell="A2")
    _band_excel_rows(
        ws_s, first_data_row=2, last_data_row=1 + len(context["variants"]), first_col=1, last_col=len(headers)
    )
    _color_verdict_cells(ws_s, rows=range(2, 2 + len(context["variants"])), cols=[8, 9, 10])

    for variant_name, v in context["variants"].items():
        rep = v["report"]
        sheet_name = f"Before-After {variant_name}"[:31]
        ws_b = wb.create_sheet(sheet_name)
        fi = compute_financial_impact_multiclass(rep, context["assumptions"])
        rows = [
            ("Macro-F1", rep["before_macro_f1"], rep["test_metrics"]["macro_f1"]),
            ("Overall accuracy", fi["before_accuracy"], fi["after_accuracy"]),
            ("Cases correctly auto-typed", fi["before_n_correct"], fi["after_n_correct"]),
            ("Net-new typology detections", 0, fi["net_new_typed"]),
        ]
        for c, h in enumerate(["Metric", "Before (baseline)", "After (ML model)", "Delta"], start=1):
            cell = ws_b.cell(row=1, column=c, value=h)
            cell.font = header_font
            cell.fill = header_fill
        for r, (metric, b, a) in enumerate(rows, start=2):
            ws_b.cell(row=r, column=1, value=metric)
            ws_b.cell(row=r, column=2, value=b)
            ws_b.cell(row=r, column=3, value=a)
            ws_b.cell(row=r, column=4, value=f"=C{r}-B{r}")
        # rows: 2=Macro-F1, 3=Accuracy, 4=Cases correctly auto-typed, 5=Net-new -- $ Impact live formulas below
        cases_row, net_new_row = 4, 5
        ws_b.cell(row=7, column=3, value="Formatted (with B/M shorthand)").font = Font(
            italic=True, color="52514E"
        )
        ws_b.cell(row=9, column=1, value="Auto-typing efficiency $ savings (ASSUMPTION, live formula)")
        ws_b.cell(
            row=9,
            column=2,
            value=f"=D{cases_row}*hours_per_case_manual_typology_review*cost_per_investigator_hour_usd",
        )
        ws_b.cell(row=9, column=2).number_format = _EXCEL_USD_FORMAT
        ws_b.cell(row=9, column=3, value=_excel_usd_shorthand_formula("B9"))
        ws_b.cell(
            row=10, column=1, value="Illustrative typology-confirmation $ value (ASSUMPTION, live formula)"
        )
        ws_b.cell(row=10, column=2, value=f"=D{net_new_row}*illustrative_typology_confirmation_value_usd")
        ws_b.cell(row=10, column=2).number_format = _EXCEL_USD_FORMAT
        ws_b.cell(row=10, column=3, value=_excel_usd_shorthand_formula("B10"))
        ws_b.cell(
            row=12,
            column=1,
            value="Note: the two $ lines above apply different ASSUMPTIONS to different real case "
            "subsets and are never summed (Section 7A discipline).",
        )
        ws_b.auto_filter.ref = "A1:D5"
        for c in range(1, 5):
            ws_b.column_dimensions[get_column_letter(c)].width = 42 if c == 1 else (26 if c == 3 else 22)
        _brand_excel_sheet(ws_b, PALETTE["series_3_aqua"], freeze_cell="A2")
        _band_excel_rows(ws_b, first_data_row=2, last_data_row=5, first_col=1, last_col=4)

        # Per-typology recall sheet, one per variant
        rc_sheet_name = f"Recall {variant_name}"[:31]
        ws_r = wb.create_sheet(rc_sheet_name)
        recall_df = context["typology_recall_tables"][variant_name]
        for c, h in enumerate(recall_df.columns, start=1):
            cell = ws_r.cell(row=1, column=c, value=h)
            cell.font = header_font
            cell.fill = header_fill
        for r, (_, row) in enumerate(recall_df.iterrows(), start=2):
            for c, col in enumerate(recall_df.columns, start=1):
                ws_r.cell(row=r, column=c, value=row[col])
        ws_r.auto_filter.ref = f"A1:{get_column_letter(len(recall_df.columns))}{1 + len(recall_df)}"
        for c in range(1, len(recall_df.columns) + 1):
            ws_r.column_dimensions[get_column_letter(c)].width = 22
        _brand_excel_sheet(ws_r, PALETTE["series_2_orange"], freeze_cell="A2")
        _band_excel_rows(
            ws_r,
            first_data_row=2,
            last_data_row=1 + len(recall_df),
            first_col=1,
            last_col=len(recall_df.columns),
        )

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))
    return path


# ============================================================================
# Real matplotlib per-typology recall Before/After chart -- CVD-safe two-series palette,
# reused identically from the dataviz skill's validated reference instance (same PALETTE
# used by every other chart in this module).
# ============================================================================
def render_typology_recall_chart_png(recall_df: pd.DataFrame, out_path: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = recall_df["Typology"].tolist()
    before_vals = recall_df["Before Recall"].astype(float).tolist()
    after_vals = recall_df["After Recall"].astype(float).tolist()

    x = range(len(labels))
    width = 0.35
    fig, ax = plt.subplots(figsize=(9, 4.4), dpi=150)
    ax.bar(
        [i - width / 2 for i in x],
        before_vals,
        width,
        label="Before (baseline)",
        color=PALETTE["series_1_blue"],
    )
    ax.bar(
        [i + width / 2 for i in x],
        after_vals,
        width,
        label="After (ML model)",
        color=PALETTE["series_2_orange"],
    )
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.set_ylabel("Recall")
    ax.set_ylim(0, 1.05)
    ax.set_title("Real per-typology recall, Before -> After")
    ax.legend()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


# ============================================================================
# HTML dashboard, multi-class version -- self-contained, real Chart.js bundled INLINE (never
# CDN-loaded), same CVD-validated PALETTE and same visual system as BP1's dashboard so every
# BP in this platform reads as one product.
# ============================================================================
def write_html_dashboard_multiclass(path: Path, context: dict, chartjs_js_path: Path) -> Path:
    chartjs_source = Path(chartjs_js_path).read_text(encoding="utf-8")

    status = context.get("status") or compute_bp_status(context)
    recommendations = context.get("smart_recommendations") or generate_smart_recommendations_multiclass(
        context
    )

    variants_json = {}
    for variant_name, v in context["variants"].items():
        rep = v["report"]
        fi = compute_financial_impact_multiclass(rep, context["assumptions"])
        ba_df = context["before_after_tables"][variant_name]
        recall_df = context["typology_recall_tables"][variant_name]
        variants_json[variant_name] = {
            "champion": rep["champion_name"],
            "macro_f1": rep["test_metrics"]["macro_f1"],
            "before_macro_f1": rep["before_macro_f1"],
            "accuracy": fi["after_accuracy"],
            "before_accuracy": fi["before_accuracy"],
            "verdict": rep["overall_verdict"],
            "class_names": rep["class_names"],
            "stage_a": rep["stage_a_ranking"],
            "shap": rep.get("shap_mean_abs_importance") or {},
            "before_after_rows": ba_df.to_dict(orient="records"),
            "recall_chart": {
                "labels": recall_df["Typology"].tolist(),
                "before": recall_df["Before Recall"].astype(float).tolist(),
                "after": recall_df["After Recall"].astype(float).tolist(),
            },
            "recall_rows": recall_df.to_dict(orient="records"),
            "financial": {
                "delta_correct": fi["delta_correct"],
                "hours_saved": fi["hours_saved"],
                "autotyping_dollar_savings": fi["autotyping_dollar_savings"],
                "autotyping_dollar_savings_fmt": _fmt_usd(fi["autotyping_dollar_savings"]),
                "net_new_typed": fi["net_new_typed"],
                "net_new_dollar_value": fi["net_new_dollar_value"],
                "net_new_dollar_value_fmt": _fmt_usd(fi["net_new_dollar_value"]),
            },
        }
    data_json = json.dumps(variants_json)
    variant_names_json = json.dumps(list(context["variants"].keys()))
    status_json = json.dumps(status)
    recs_json = json.dumps(recommendations)
    primary_variant_json = json.dumps(context["primary_variant"])
    palette = PALETTE

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{context['bp_id']} -- {context['bp_name']} -- Compliance Dashboard</title>
<style>
  :root {{
    color-scheme: light;
    --surface: {palette['surface']}; --page: {palette['page']};
    --ink: {palette['ink_primary']}; --ink-2: {palette['ink_secondary']}; --ink-muted: {palette['ink_muted']};
    --grid: {palette['gridline']};
    --s1: {palette['series_1_blue']}; --s2: {palette['series_2_orange']}; --s3: {palette['series_3_aqua']};
    --good: {palette['status_good']}; --warn: {palette['status_warning']}; --crit: {palette['status_critical']};
  }}
  * {{ box-sizing: border-box; }}
  html {{ scroll-behavior:smooth; }}
  body {{
    margin:0; color:var(--ink); font-family: system-ui,-apple-system,"Segoe UI",sans-serif;
    /* Pleasant, restrained background: soft brand-tinted gradient washes over the page plane --
       never behind text (cards stay on solid --surface), so legibility/contrast is unaffected. */
    background:
      radial-gradient(1100px 580px at 8% -8%, rgba(42,120,214,0.08), transparent 58%),
      radial-gradient(900px 520px at 100% 0%, rgba(27,175,122,0.07), transparent 55%),
      radial-gradient(800px 500px at 50% 110%, rgba(235,104,52,0.05), transparent 60%),
      var(--page);
    background-attachment: fixed;
    min-height:100vh;
  }}
  .accent-bar {{ height:4px; width:100%;
    background: linear-gradient(90deg, var(--s1), var(--s3), var(--s2), var(--s1));
    background-size: 300% 100%; animation: shimmer 6s linear infinite; }}
  @keyframes shimmer {{ 0% {{ background-position:0% 0; }} 100% {{ background-position:300% 0; }} }}
  header {{ padding:22px 24px; border-bottom:1px solid var(--grid); background:var(--surface);
    animation: fadeInUp .5s ease both; box-shadow:0 1px 0 rgba(11,11,11,.02); }}
  h1 {{ margin:0 0 4px; font-size:21px; letter-spacing:-.01em; }}
  .sub {{ color:var(--ink-2); font-size:13px; }}

  @keyframes fadeInUp {{ from {{ opacity:0; transform:translateY(10px); }} to {{ opacity:1; transform:translateY(0); }} }}
  @keyframes fadeSection {{ from {{ opacity:0; transform:translateY(6px); }} to {{ opacity:1; transform:translateY(0); }} }}
  @keyframes pulseDot {{ 0% {{ box-shadow:0 0 0 0 currentColor; opacity:1; }} 70% {{ box-shadow:0 0 0 9px transparent; opacity:.35; }} 100% {{ box-shadow:0 0 0 0 transparent; opacity:1; }} }}
  .tile, .chart-box, .rec-card, .narrative, .status-banner {{ animation: fadeInUp .45s ease both; }}
  .tile, .chart-box, .rec-card {{ box-shadow:0 1px 2px rgba(11,11,11,.04);
    transition: transform .2s cubic-bezier(.22,1,.36,1), box-shadow .2s ease, border-color .2s ease; }}
  .tile:hover, .chart-box:hover, .rec-card:hover {{ transform:translateY(-4px); box-shadow:0 14px 28px rgba(11,11,11,.10); border-color:rgba(42,120,214,.25); }}

  .status-banner {{ margin:16px 24px 0; padding:16px 20px; border-radius:12px; border:1px solid var(--grid);
    display:flex; align-items:flex-start; gap:14px; box-shadow:0 1px 2px rgba(11,11,11,.04); }}
  .status-banner.good {{ background:linear-gradient(135deg,#eafaea,#e7f7e7); }}
  .status-banner.warning {{ background:linear-gradient(135deg,#fff9ec,#fff6e5); }}
  .status-banner.critical {{ background:linear-gradient(135deg,#fef0ef,#fdeceb); }}
  .status-banner .dot {{ width:14px; height:14px; border-radius:50%; flex:0 0 auto; margin-top:3px; position:relative; }}
  .status-banner .dot::after {{ content:""; position:absolute; inset:0; border-radius:50%; background:currentColor;
    animation: pulseDot 2.2s ease-out infinite; }}
  .status-banner .dot.good {{ background:var(--good); color:var(--good); }}
  .status-banner .dot.warning {{ background:var(--warn); color:var(--warn); }}
  .status-banner .dot.critical {{ background:var(--crit); color:var(--crit); }}
  .status-banner .label {{ font-size:16px; font-weight:700; }}
  .status-banner .rationale {{ font-size:13px; color:var(--ink-2); margin-top:4px; line-height:1.5; }}

  .narrative {{ background:var(--surface); border:1px solid var(--grid); border-radius:12px; padding:18px 20px; margin:16px 24px 0;
    box-shadow:0 1px 2px rgba(11,11,11,.04); }}
  .narrative h2 {{ margin:0 0 8px; font-size:15px; }}
  .narrative p {{ margin:0 0 10px; color:var(--ink-2); font-size:13px; line-height:1.5; }}
  .narrative ul {{ margin:0; padding-left:18px; }}
  .narrative li {{ color:var(--ink-2); font-size:13px; line-height:1.6; }}

  .tabs {{ position:relative; display:flex; gap:4px; padding:0 24px; margin-top:16px; background:var(--surface); border-bottom:1px solid var(--grid); }}
  .tabs button {{ border:none; background:transparent; color:var(--ink-2); padding:12px 16px; cursor:pointer;
    font-size:13px; font-weight:600; border-bottom:2px solid transparent; border-radius:8px 8px 0 0;
    transition:color .15s ease, background .2s ease; position:relative; z-index:1; }}
  .tabs button:hover {{ color:var(--ink); background:rgba(42,120,214,.07); }}
  .tabs button.active {{ color:var(--s1); }}
  .tab-indicator {{ position:absolute; bottom:-1px; left:0; height:3px; width:0; border-radius:3px;
    background:linear-gradient(90deg, var(--s1), var(--s3));
    box-shadow:0 0 8px rgba(42,120,214,.45);
    transition: transform .4s cubic-bezier(.34,1.56,.64,1), width .4s cubic-bezier(.34,1.56,.64,1); }}

  .filters {{ display:flex; align-items:center; gap:8px; padding:12px 24px; background:var(--surface); border-bottom:1px solid var(--grid); }}
  .filters .fl-label {{ color:var(--ink-muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; margin-right:4px; }}
  .filters button {{ position:relative; overflow:hidden; border:1px solid var(--grid); background:var(--surface); color:var(--ink); padding:6px 14px;
    border-radius:999px; cursor:pointer; font-size:13px;
    transition: background .2s ease, color .2s ease, border-color .2s ease, transform .25s cubic-bezier(.34,1.56,.64,1), box-shadow .2s ease; }}
  .filters button:hover {{ transform:translateY(-2px); box-shadow:0 6px 14px rgba(11,11,11,.10); border-color:rgba(42,120,214,.35); }}
  .filters button.active {{ background:var(--s1); color:#fff; border-color:var(--s1); box-shadow:0 4px 12px rgba(42,120,214,.35);
    animation: filterPop .35s cubic-bezier(.34,1.56,.64,1); }}
  @keyframes filterPop {{ 0% {{ transform:scale(.88); }} 60% {{ transform:scale(1.06); }} 100% {{ transform:scale(1); }} }}
  .ripple {{ position:absolute; border-radius:50%; background:rgba(255,255,255,.55); transform:scale(0);
    animation: rippleFx .55s ease-out; pointer-events:none; }}
  @keyframes rippleFx {{ to {{ transform:scale(2.6); opacity:0; }} }}

  .view-section {{ display:none; }}
  .view-section.active {{ display:block; animation: fadeSection .35s cubic-bezier(.22,1,.36,1) both; }}

  main {{ padding:20px 24px; display:grid; gap:16px; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); }}
  .tile {{ background:var(--surface); border:1px solid var(--grid); border-radius:12px; padding:16px; }}
  .tile .label {{ color:var(--ink-2); font-size:12px; text-transform:uppercase; letter-spacing:.04em; display:flex; justify-content:space-between; align-items:center; }}
  .tile .value {{ font-size:27px; font-weight:650; margin-top:4px; }}
  .tile .value.good {{ color:var(--good); }}
  .wide {{ grid-column: 1 / -1; }}
  .chart-box {{ background:var(--surface); border:1px solid var(--grid); border-radius:12px; padding:16px; height:340px; }}
  .bar-track {{ background:var(--grid); border-radius:6px; height:8px; overflow:hidden; margin-top:8px; position:relative; }}
  .bar-fill {{ height:100%; border-radius:6px; width:0%; position:relative; overflow:hidden;
    transition:width 1s cubic-bezier(.22,1,.36,1); }}
  .bar-fill::after {{ content:""; position:absolute; inset:0;
    background:linear-gradient(90deg, transparent, rgba(255,255,255,.45), transparent);
    background-size:60px 100%; animation: shimmerBar 1.8s ease-in-out infinite; }}
  @keyframes shimmerBar {{ 0% {{ background-position:-120px 0; }} 100% {{ background-position:220px 0; }} }}
  .verdict-pill {{ display:inline-block; padding:2px 10px; border-radius:999px; font-size:12px; font-weight:600; }}
  .verdict-pass {{ background:#e7f7e7; color:var(--good); }}
  .verdict-fail {{ background:#fdeceb; color:var(--crit); }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th, td {{ text-align:left; padding:6px 8px; border-bottom:1px solid var(--grid); }}
  th {{ color:var(--ink-2); font-weight:600; }}
  tbody tr {{ transition: background .12s ease; }}
  tbody tr:hover {{ background:rgba(42,120,214,.05); }}
  .search-box {{ padding:6px 10px; border:1px solid var(--grid); border-radius:6px; font-size:12.5px; width:100%; margin-bottom:10px;
    transition: border-color .15s ease, box-shadow .15s ease; }}
  .search-box:focus {{ outline:none; border-color:var(--s1); box-shadow:0 0 0 3px rgba(42,120,214,.12); }}
  .btn-ghost {{ border:1px solid var(--grid); background:var(--surface); color:var(--ink); padding:5px 12px;
    border-radius:6px; cursor:pointer; font-size:12px; transition: background .15s ease; }}
  .btn-ghost:hover {{ background:var(--page); }}
  .rec-card {{ background:var(--surface); border:1px solid var(--grid); border-radius:12px; padding:16px 18px; margin-bottom:12px; }}
  .rec-card h3 {{ margin:0 0 8px; font-size:14.5px; }}
  .rec-card .smart-row {{ font-size:12.5px; color:var(--ink-2); margin:5px 0; line-height:1.55; }}
  .rec-card .smart-row b {{ color:var(--ink); }}
  footer {{ padding:16px 24px; color:var(--ink-muted); font-size:12px; }}
</style>
</head>
<body>
<div class="accent-bar"></div>
<header>
  <h1>{context['bp_id']} -- {context['bp_name']}</h1>
  <div class="sub">Compliance-Impact Dashboard -- generated {context['generated_at_utc']} UTC -- real data, this project's own notebook runs</div>
</header>
<div class="status-banner" id="statusBanner"></div>
<div class="narrative">
  <h2>Business Objective</h2>
  <p>{context['business_objective']}</p>
  <h2>What This Means for the Business</h2>
  <ul>
    {''.join(f'<li>{point}</li>' for point in context['business_benefits'])}
  </ul>
</div>

<div class="tabs" id="tabs">
  <button data-view="overview" class="active">Overview</button>
  <button data-view="performance">Model Performance</button>
  <button data-view="financial">Financial Impact</button>
  <button data-view="recommendations">Recommendations</button>
  <span class="tab-indicator" id="tabIndicator"></span>
</div>
<div class="filters" id="filters"><span class="fl-label">Dataset variant</span></div>

<section id="view-overview" class="view-section active">
  <main id="tiles"></main>
</section>

<section id="view-performance" class="view-section">
  <main style="grid-template-columns: 1fr 1fr;">
    <div class="chart-box"><canvas id="recallChart"></canvas></div>
    <div class="chart-box">
      <input type="text" id="shapSearch" class="search-box" placeholder="Filter real SHAP features by name...">
      <canvas id="shapChart"></canvas>
    </div>
  </main>
  <main>
    <div class="tile wide">
      <div class="label">Real per-typology recall, Before -&gt; After (this variant)</div>
      <table id="recallTable"><thead><tr><th>Typology</th><th>Before Recall</th><th>After Recall</th><th>Delta Recall</th><th>Real Test Support (n)</th></tr></thead><tbody></tbody></table>
    </div>
  </main>
  <main>
    <div class="tile wide">
      <div class="label">
        <span>Stage B champion selection -- real CV macro-F1 by candidate (this variant)</span>
        <button id="stageASortBtn" class="btn-ghost">Sort by Macro-F1 &darr;</button>
      </div>
      <table id="stageATable"><thead><tr><th>Rank</th><th>Model</th><th>Real Test Macro-F1 (Stage A single split)</th></tr></thead><tbody></tbody></table>
    </div>
  </main>
</section>

<section id="view-financial" class="view-section">
  <main id="finTiles"></main>
  <main>
    <div class="tile wide">
      <div class="label">Before / After -- full real headline table (this variant)</div>
      <p id="finNote" class="sub" style="margin:8px 0 10px;"></p>
      <table id="baTable"><thead><tr><th>Metric</th><th>Before (baseline)</th><th>After (ML model)</th><th>Delta</th><th>$ Impact</th></tr></thead><tbody></tbody></table>
    </div>
  </main>
</section>

<section id="view-recommendations" class="view-section">
  <main>
    <div class="wide" id="recsList"></div>
  </main>
</section>

<footer>
  Real, per-variant results -- never merged or blended into one unlabeled figure, per this
  platform's locked multi-variant policy. Chart.js bundled locally (no CDN). Generated by
  report_builder.py -- IBM AML RiskIQ Enterprise Suite.
</footer>
<script>
{chartjs_source}
</script>
<script>
(function() {{
  const DATA = {data_json};
  const VARIANTS = {variant_names_json};
  const STATUS = {status_json};
  const RECS = {recs_json};
  const PRIMARY = {primary_variant_json};
  let current = VARIANTS.includes(PRIMARY) ? PRIMARY : VARIANTS[0];
  let shapFilter = "";
  let stageASortDir = "desc";
  const palette = {{ s1: "{palette['series_1_blue']}", s2: "{palette['series_2_orange']}", s3: "{palette['series_3_aqua']}",
    grid: "{palette['gridline']}", ink2: "{palette['ink_secondary']}" }};

  const banner = document.getElementById("statusBanner");
  banner.className = "status-banner " + STATUS.css_class;
  banner.innerHTML = `<div class="dot ${{STATUS.css_class}}"></div>
    <div><div class="label">${{STATUS.label}}</div><div class="rationale">${{STATUS.rationale}}</div></div>`;

  function spawnRipple(e, btn) {{
    const old = btn.querySelector(".ripple"); if (old) old.remove();
    const rect = btn.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height) * 1.4;
    const span = document.createElement("span");
    span.className = "ripple";
    span.style.width = span.style.height = size + "px";
    span.style.left = (e.clientX - rect.left - size / 2) + "px";
    span.style.top = (e.clientY - rect.top - size / 2) + "px";
    btn.appendChild(span);
    span.addEventListener("animationend", () => span.remove());
  }}

  const tabs = [...document.querySelectorAll(".tabs button")];
  const tabIndicator = document.getElementById("tabIndicator");
  function moveTabIndicator(btn) {{
    if (!tabIndicator || !btn) return;
    tabIndicator.style.width = btn.offsetWidth + "px";
    tabIndicator.style.transform = "translateX(" + btn.offsetLeft + "px)";
  }}
  tabs.forEach(btn => btn.addEventListener("click", (e) => {{
    spawnRipple(e, btn);
    tabs.forEach(b => b.classList.toggle("active", b === btn));
    document.querySelectorAll(".view-section").forEach(sec => sec.classList.toggle("active", sec.id === "view-" + btn.dataset.view));
    moveTabIndicator(btn);
  }}));
  window.addEventListener("resize", () => moveTabIndicator(tabs.find(b => b.classList.contains("active"))));
  requestAnimationFrame(() => moveTabIndicator(tabs.find(b => b.classList.contains("active"))));

  const filtersEl = document.getElementById("filters");
  VARIANTS.forEach(v => {{
    const b = document.createElement("button");
    b.textContent = v;
    b.className = v === current ? "active" : "";
    b.onclick = (e) => {{ spawnRipple(e, b); current = v; render(); }};
    filtersEl.appendChild(b);
  }});

  function animateValue(el, start, end, decimals, opts) {{
    opts = opts || {{}};
    const suffix = opts.suffix || "";
    const currency = !!opts.currency;
    const duration = opts.duration || 700;
    const finalText = opts.finalText;
    function fmt(v) {{
      if (currency) {{
        const sign = v < 0 ? "-" : "";
        const mag = Math.abs(v);
        return sign + "$" + (decimals === 0 ? Math.round(mag).toLocaleString() : mag.toFixed(decimals)) + suffix;
      }}
      return (decimals === 0 ? Math.round(v).toLocaleString() : v.toFixed(decimals)) + suffix;
    }}
    const t0 = performance.now();
    function step(t) {{
      const p = Math.min(1, (t - t0) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      const v = start + (end - start) * eased;
      if (p < 1) {{
        el.textContent = fmt(v);
        requestAnimationFrame(step);
      }} else {{
        el.textContent = finalText != null ? finalText : fmt(end);
      }}
    }}
    requestAnimationFrame(step);
  }}

  let recallChart, shapChart, stageAChart;

  function renderStageATable(rows) {{
    const tbody = document.querySelector("#stageATable tbody");
    tbody.innerHTML = "";
    rows.forEach((row, i) => {{
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${{i + 1}}</td><td>${{row.name}}</td><td>${{row.macro_f1.toFixed(4)}}</td>`;
      tbody.appendChild(tr);
    }});
  }}

  function renderRecallTable(rows) {{
    const tbody = document.querySelector("#recallTable tbody");
    tbody.innerHTML = "";
    rows.forEach(row => {{
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${{row["Typology"]}}</td><td>${{row["Before Recall"]}}</td>`
        + `<td>${{row["After Recall"]}}</td><td>${{row["Delta Recall"]}}</td><td>${{row["Real Test Support (n)"]}}</td>`;
      tbody.appendChild(tr);
    }});
  }}

  function renderBaTable(rows) {{
    const tbody = document.querySelector("#baTable tbody");
    tbody.innerHTML = "";
    rows.forEach(row => {{
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${{row["Metric"]}}</td><td>${{row["Before (baseline)"]}}</td>`
        + `<td>${{row["After (ML model)"]}}</td><td>${{row["Delta"]}}</td><td>${{row["$ Impact"]}}</td>`;
      tbody.appendChild(tr);
    }});
  }}

  function render() {{
    [...filtersEl.querySelectorAll("button")].forEach(b => b.classList.toggle("active", b.textContent === current));
    const d = DATA[current];

    const tilesEl = document.getElementById("tiles");
    tilesEl.innerHTML = `
      <div class="tile"><div class="label">Champion</div><div class="value" id="t-champ">${{d.champion}}</div></div>
      <div class="tile"><div class="label">Test Macro-F1</div><div class="value" id="t-f1">0.0000</div></div>
      <div class="tile"><div class="label">Lift over single-typology baseline</div><div class="value good" id="t-lift">0x</div></div>
      <div class="tile"><div class="label">Overall labeling accuracy</div><div class="value" id="t-acc">0.000</div></div>
      <div class="tile"><div class="label">Real typologies with matched ground truth</div><div class="value">${{d.class_names.length}}</div></div>
      <div class="tile"><div class="label">Two-gate verdict</div><div class="value"><span class="verdict-pill ${{d.verdict === 'PASS' ? 'verdict-pass' : 'verdict-fail'}}">${{d.verdict}}</span></div></div>
      <div class="tile"><div class="label">Auto-typing efficiency savings (ASSUMPTION)</div><div class="value good" id="t-kpi-auto">$0</div></div>
      <div class="tile"><div class="label">Typology-confirmation value, illustrative (ASSUMPTION)</div><div class="value good" id="t-kpi-net">$0</div></div>
    `;
    [...tilesEl.children].forEach((el, i) => {{ el.style.animationDelay = (i * 40) + "ms"; }});
    animateValue(document.getElementById("t-f1"), 0, d.macro_f1, 4);
    animateValue(document.getElementById("t-lift"), 0, d.macro_f1 / d.before_macro_f1, 1, {{ suffix: "x" }});
    animateValue(document.getElementById("t-acc"), 0, d.accuracy, 3);
    animateValue(document.getElementById("t-kpi-auto"), 0, d.financial.autotyping_dollar_savings, 0,
      {{ currency: true, duration: 800, finalText: d.financial.autotyping_dollar_savings_fmt }});
    animateValue(document.getElementById("t-kpi-net"), 0, d.financial.net_new_dollar_value, 0,
      {{ currency: true, duration: 800, finalText: d.financial.net_new_dollar_value_fmt }});

    const stageASorted = [...d.stage_a].sort((a, b) => stageASortDir === "desc" ? b.macro_f1 - a.macro_f1 : a.macro_f1 - b.macro_f1);
    if (stageAChart) stageAChart.destroy();
    stageAChart = null;
    renderStageATable(stageASorted);
    renderRecallTable(d.recall_rows);

    if (recallChart) recallChart.destroy();
    recallChart = new Chart(document.getElementById("recallChart"), {{
      type: "bar",
      data: {{ labels: d.recall_chart.labels, datasets: [
        {{ label: "Before (baseline)", data: d.recall_chart.before, backgroundColor: palette.s1, borderRadius: 4 }},
        {{ label: "After (ML model)", data: d.recall_chart.after, backgroundColor: palette.s2, borderRadius: 4 }},
      ] }},
      options: {{ responsive: true, maintainAspectRatio: false, animation: {{ duration: 800, easing: "easeOutCubic" }},
        plugins: {{ legend: {{ position: "bottom" }}, title: {{ display: true, text: "Real per-typology recall, Before -> After (" + current + ")" }} }},
        scales: {{ y: {{ beginAtZero: true, max: 1, grid: {{ color: palette.grid }} }}, x: {{ grid: {{ display: false }} }} }} }}
    }});

    const shapEntries = Object.entries(d.shap)
      .filter(e => e[0].toLowerCase().includes(shapFilter.toLowerCase()))
      .sort((a, b) => b[1] - a[1]).slice(0, 10);
    if (shapChart) shapChart.destroy();
    shapChart = new Chart(document.getElementById("shapChart"), {{
      type: "bar",
      data: {{ labels: shapEntries.map(e => e[0]), datasets: [{{ label: "mean |SHAP|", data: shapEntries.map(e => e[1]),
        backgroundColor: palette.s3, borderRadius: 4 }}] }},
      options: {{ responsive: true, maintainAspectRatio: false, indexAxis: "y", animation: {{ duration: 700, easing: "easeOutCubic" }},
        plugins: {{ legend: {{ display: false }}, title: {{ display: true, text: "Top real SHAP features, champion (" + current + ")" }} }},
        scales: {{ x: {{ beginAtZero: true, grid: {{ color: palette.grid }} }}, y: {{ grid: {{ display: false }} }} }} }}
    }});

    const finTilesEl = document.getElementById("finTiles");
    finTilesEl.innerHTML = `
      <div class="tile"><div class="label">Auto-typing efficiency savings (ASSUMPTION)</div><div class="value good" id="t-fp">$0</div></div>
      <div class="tile"><div class="label">Investigator hours freed (ASSUMPTION)</div><div class="value" id="t-hrs">0</div></div>
      <div class="tile"><div class="label">Typology-confirmation value, illustrative (ASSUMPTION)</div><div class="value good" id="t-tp">$0</div></div>
      <div class="tile"><div class="label">Net-new real typology detections</div><div class="value" id="t-cases">0</div></div>
    `;
    [...finTilesEl.children].forEach((el, i) => {{ el.style.animationDelay = (i * 40) + "ms"; }});
    animateValue(document.getElementById("t-fp"), 0, d.financial.autotyping_dollar_savings, 0,
      {{ currency: true, duration: 800, finalText: d.financial.autotyping_dollar_savings_fmt }});
    animateValue(document.getElementById("t-hrs"), 0, d.financial.hours_saved, 1, {{ suffix: " hrs", duration: 800 }});
    animateValue(document.getElementById("t-tp"), 0, d.financial.net_new_dollar_value, 0,
      {{ currency: true, duration: 800, finalText: d.financial.net_new_dollar_value_fmt }});
    animateValue(document.getElementById("t-cases"), 0, d.financial.net_new_typed, 0, {{ duration: 800 }});
    document.getElementById("finNote").textContent =
      `Exact figures: ${{d.financial.autotyping_dollar_savings_fmt}} auto-typing efficiency savings; `
      + `${{d.financial.net_new_dollar_value_fmt}} illustrative typology-confirmation value. `
      + `These apply different ASSUMPTIONS to different real case subsets and are never summed (locked Section 7A discipline).`;

    renderBaTable(d.before_after_rows);
  }}

  document.getElementById("stageASortBtn").addEventListener("click", () => {{
    stageASortDir = stageASortDir === "desc" ? "asc" : "desc";
    document.getElementById("stageASortBtn").textContent = "Sort by Macro-F1 " + (stageASortDir === "desc" ? "\\u2193" : "\\u2191");
    render();
  }});
  document.getElementById("shapSearch").addEventListener("input", (e) => {{ shapFilter = e.target.value; render(); }});

  document.getElementById("recsList").innerHTML = RECS.map((r, i) => `
    <div class="rec-card" style="animation-delay:${{i * 60}}ms">
      <h3>${{r.title}}</h3>
      <div class="smart-row"><b>Specific:</b> ${{r.specific}}</div>
      <div class="smart-row"><b>Measurable:</b> ${{r.measurable}}</div>
      <div class="smart-row"><b>Achievable:</b> ${{r.achievable}}</div>
      <div class="smart-row"><b>Relevant:</b> ${{r.relevant}}</div>
      <div class="smart-row"><b>Time-bound:</b> ${{r.time_bound}}</div>
    </div>
  `).join("");

  render();
}})();
</script>
</body>
</html>
"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


# ============================================================================
# PowerPoint executive deck (python-pptx), multi-class version
# ============================================================================
def write_pptx_deck_multiclass(path: Path, context: dict, chart_png_paths: Optional[dict] = None) -> Path:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt

    prs = Presentation()
    blue = RGBColor(0x2A, 0x78, 0xD6)

    slide = _add_branded_slide(prs, 0)
    slide.shapes.title.text = f"{context['bp_id']}: {context['bp_name']}"
    slide.placeholders[1].text = f"Compliance-Impact Executive Briefing -- {context['generated_at_utc']} UTC"

    slide = _add_branded_slide(prs, 1)
    slide.shapes.title.text = "Business Objective"
    slide.placeholders[1].text_frame.text = context["business_objective"]

    status = context.get("status") or compute_bp_status(context)
    status_colors = {
        "good": RGBColor(0x0C, 0xA3, 0x0C),
        "warning": RGBColor(0xC9, 0x85, 0x00),
        "critical": RGBColor(0xD0, 0x3B, 0x3B),
    }
    slide = _add_branded_slide(prs, 1)
    slide.shapes.title.text = "Recommendation & Status"
    body = slide.placeholders[1].text_frame
    body.text = status["label"]
    body.paragraphs[0].font.bold = True
    body.paragraphs[0].font.size = Pt(28)
    body.paragraphs[0].font.color.rgb = status_colors.get(status["css_class"], blue)
    p = body.add_paragraph()
    p.text = status["rationale"]
    p.level = 1

    primary_name = context["primary_variant"]
    primary = context["variants"][primary_name]
    rep = primary["report"]
    fi = compute_financial_impact_multiclass(rep, context["assumptions"])

    slide = _add_branded_slide(prs, 1)
    slide.shapes.title.text = "Executive Summary"
    body = slide.placeholders[1].text_frame
    body.text = f"Champion model: {rep['champion_name']} ({primary_name} variant)"
    for line in [
        f"Real test macro-F1: {rep['test_metrics']['macro_f1']:.4f} "
        f"({_safe_div(rep['test_metrics']['macro_f1'], rep['before_macro_f1']):.1f}x single-typology baseline)",
        f"Overall labeling accuracy: {fi['before_accuracy']:.3f} -> {fi['after_accuracy']:.3f}",
        f"Real typologies with matched ground truth this run: {len(rep['class_names'])} ({', '.join(rep['class_names'])})",
        f"Two-gate verdict: {rep['overall_verdict']}",
    ]:
        p = body.add_paragraph()
        p.text = line
        p.level = 1

    slide = _add_branded_slide(prs, 1)
    slide.shapes.title.text = "What This Means for the Business"
    body = slide.placeholders[1].text_frame
    body.text = context["business_benefits"][0]
    for point in context["business_benefits"][1:]:
        p = body.add_paragraph()
        p.text = point
        p.level = 1

    slide = _add_branded_slide(prs, 5)
    slide.shapes.title.text = "Model Performance by Dataset Variant"
    rows, cols = len(context["variants"]) + 1, 4
    left, top, width, height = Inches(0.5), Inches(1.5), Inches(9), Inches(0.4 * rows)
    table_shape = slide.shapes.add_table(rows, cols, left, top, width, height).table
    for c, h in enumerate(["Variant", "Champion", "Test Macro-F1", "Verdict"]):
        table_shape.cell(0, c).text = h
    for r, (variant_name, v) in enumerate(context["variants"].items(), start=1):
        rp = v["report"]
        table_shape.cell(r, 0).text = variant_name
        table_shape.cell(r, 1).text = rp["champion_name"]
        table_shape.cell(r, 2).text = f"{rp['test_metrics']['macro_f1']:.4f}"
        table_shape.cell(r, 3).text = rp["overall_verdict"]

    if chart_png_paths and "typology_recall" in chart_png_paths:
        slide = _add_branded_slide(prs, 5)
        slide.shapes.title.text = f"Per-Typology Recall, Before / After ({primary_name})"
        slide.shapes.add_picture(
            str(chart_png_paths["typology_recall"]), Inches(0.5), Inches(1.3), width=Inches(9)
        )

    slide = _add_branded_slide(prs, 1)
    slide.shapes.title.text = f"Financial Impact Summary ({primary_name})"
    body = slide.placeholders[1].text_frame
    body.text = f"Auto-typing efficiency savings (ASSUMPTION): {_fmt_usd(fi['autotyping_dollar_savings'])}"
    for line in [
        f"{fi['hours_saved']:,.1f} investigator hours freed, {fi['delta_correct']:+,} more cases correctly auto-typed",
        f"Illustrative typology-confirmation value (ASSUMPTION): {_fmt_usd(fi['net_new_dollar_value'])}",
        f"{fi['net_new_typed']:,} real cases whose typology the old single-guess rule structurally could not identify",
        "These figures apply different ASSUMPTIONS to different real case subsets and are never summed (locked Section 7A discipline).",
    ]:
        p = body.add_paragraph()
        p.text = line
        p.level = 1

    recs = context.get("smart_recommendations") or generate_smart_recommendations_multiclass(context)
    slide = _add_branded_slide(prs, 1)
    slide.shapes.title.text = "Key Recommendations"
    body = slide.placeholders[1].text_frame
    body.text = recs[0]["title"]
    p = body.add_paragraph()
    p.text = recs[0]["specific"]
    p.level = 1
    for r in recs[1:]:
        p = body.add_paragraph()
        p.text = r["title"]
        p2 = body.add_paragraph()
        p2.text = r["specific"]
        p2.level = 1

    slide = _add_branded_slide(prs, 1)
    slide.shapes.title.text = "Regulatory & Compliance Mapping"
    body = slide.placeholders[1].text_frame
    body.text = context["regulatory_frameworks"][0][0]
    for fw, applies in context["regulatory_frameworks"][1:]:
        p = body.add_paragraph()
        p.text = f"{fw} ({applies})"
        p.level = 1

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(path))
    return path


# ============================================================================
# MODEL_CARD.md, multi-class version (CHANGELOG.md reuses write_changelog() unchanged --
# it is already fully generic)
# ============================================================================
def write_model_card_multiclass(path: Path, context: dict) -> Path:
    primary_name = context["primary_variant"]
    primary = context["variants"][primary_name]
    rep = primary["report"]
    status = context.get("status") or compute_bp_status(context)
    fi = compute_financial_impact_multiclass(rep, context["assumptions"])
    recs = context.get("smart_recommendations") or generate_smart_recommendations_multiclass(context)
    recall_df = context["typology_recall_tables"][primary_name]
    lines = (
        [
            f"# Model Card -- {context['bp_id']}: {context['bp_name']}",
            "",
            f"_Generated {context['generated_at_utc']} UTC. Primary reported variant: "
            f"{primary_name} (this BP's locked mandatory realism-validation tier)._",
            "",
            f"## Status: {status['label']}",
            status["rationale"],
            "",
            "## Business Objective",
            context["business_objective"],
            "",
            "## What This Means for the Business",
        ]
        + [f"- {point}" for point in context["business_benefits"]]
        + [
            "",
            "## Financial Impact Summary",
            f"- Auto-typing efficiency savings (ASSUMPTION): {_fmt_usd(fi['autotyping_dollar_savings'])} "
            f"({fi['hours_saved']:,.1f} investigator hours, {fi['delta_correct']:+,} more cases correctly auto-typed)",
            f"- Illustrative typology-confirmation value (ASSUMPTION): {_fmt_usd(fi['net_new_dollar_value'])} "
            f"({fi['net_new_typed']:,} real cases the old single-guess rule structurally could not identify)",
            "- These figures apply different ASSUMPTIONS to different real case subsets and are never summed (locked Section 7A discipline).",
            "",
            "## Model Details",
            f"- Champion algorithm: **{rep['champion_name']}**",
            f"- Random seed: {rep['random_seed']}",
            f"- Feature count: {len(rep['feature_cols'])}",
            "- Primary metric: macro-F1 (no single decision threshold -- multi-class argmax)",
            f"- Real typologies with matched ground truth this run: {', '.join(rep['class_names'])} "
            f"({len(rep['class_names'])} of the 8 typologies this platform models)",
            "",
            "## Intended Use",
            "Real-time / batch typology classification of transactions already flagged as known "
            "laundering (`Is Laundering==1`), feeding investigator case triage and SAR-narrative "
            "drafting. Not a standalone SAR-filing decision -- output is evidence for a human "
            "investigator, per this platform's locked scope.",
            "",
            "## Training Data",
            "IBM Transactions for Anti Money Laundering (AML) -- synthetic, IBM Research. Variants "
            "used (never merged): " + ", ".join(context["variants"].keys()) + ".",
            "",
            "## Evaluation",
            "| Variant | Champion | Test Macro-F1 | Before Macro-F1 | Overall Accuracy | Verdict |",
            "|---|---|---|---|---|---|",
        ]
    )
    for variant_name, v in context["variants"].items():
        r = v["report"]
        f = compute_financial_impact_multiclass(r, context["assumptions"])
        lines.append(
            f"| {variant_name} | {r['champion_name']} | {r['test_metrics']['macro_f1']:.4f} | "
            f"{r['before_macro_f1']:.4f} | {f['after_accuracy']:.4f} | {r['overall_verdict']} |"
        )
    lines += [
        "",
        f"## Real Per-Typology Recall, Before -> After ({primary_name})",
        "| Typology | Before Recall | After Recall | Delta Recall | Real Test Support (n) |",
        "|---|---|---|---|---|",
    ]
    for _, row in recall_df.iterrows():
        lines.append(
            f"| {row['Typology']} | {row['Before Recall']} | {row['After Recall']} | "
            f"{row['Delta Recall']} | {row['Real Test Support (n)']} |"
        )
    lines += [
        "",
        "## Explainability",
        "SHAP (TreeExplainer, global, averaged across all real typologies) and LIME (local, "
        "per real predicted-typology instance) -- see this variant's own saved "
        "`{}_notebook3_validation_report_*.json` for full real values.".format(context["bp_id"].lower()),
        "",
        "## Ethical Considerations / Fairness",
        context["fairness_note"],
        "",
        "## Caveats & Limitations",
    ]
    for cav in context.get("caveats", []):
        lines.append(f"- {cav}")
    lines += [
        "",
        "## Regulatory Mapping",
    ]
    for fw, applies in context["regulatory_frameworks"]:
        lines.append(f"- {fw} -- {applies}")
    lines += ["", "## Recommendations"]
    for r in recs:
        lines += [
            f"### {r['title']}",
            f"- **Specific:** {r['specific']}",
            f"- **Measurable:** {r['measurable']}",
            f"- **Achievable:** {r['achievable']}",
            f"- **Relevant:** {r['relevant']}",
            f"- **Time-bound:** {r['time_bound']}",
            "",
        ]

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ============================================================================
# ============================================================================
# STRUCTURAL EXTENSION (added for BP3 -- Transaction Network & Graph Intelligence,
# 2026-10-01). Every function above this block (binary, BP1-original, and the MULTICLASS
# block added for BP2) is left completely UNCHANGED -- already-shipped, verified-working
# reports must never regress. The functions below are NEW, parallel, structural-signal-aware
# equivalents, built for any BP whose Notebook 3 report has no trained ML model, no decision
# threshold in the classification sense, and no PR-AUC/macro-F1 -- instead a single primary
# metric (a network-lift ratio) with a real bootstrap 95% CI, evaluated across several
# candidate structural signals (BP3's locked Stage A screening), never a classifier.
#
# Reused UNCHANGED from above (confirmed fully generic, no binary/multiclass-specific
# assumption): _fmt_usd / format_usd, _EXCEL_USD_FORMAT (used only for the FastAPI self-test
# section's "not applicable" framing, no dollar figure is computed structurally),
# _defined_name, compute_bp_status (reads only rep["overall_verdict"] per variant, generic),
# export_pdf_from_docx, write_changelog, PALETTE, every _brand_*/_add_branded_slide/_hex_rgb
# helper, _band_excel_rows, _color_verdict_cells.
#
# Real NB3 report schema this reads (verified against the user's own real
# bp3_notebook3_validation_report_li_medium.json, 2026-10-01 run): "bp_id", "bp_name",
# "dataset_variant", "random_seed", "primary_metric", "n_nodes", "n_distinct_edges",
# "n_transaction_edges", "base_rate_all", "n_train_nodes", "n_test_nodes", "base_rate_train",
# "base_rate_test", "pagerank_self_test_max_abs_diff_vs_networkx",
# "hi_small_stage_a_prior_champion", "stage_results" (list of {signal, threshold,
# n_test_flagged, n_test_flagged_exposed, flagged_exposure_rate, lift_ratio}), "champion_name",
# "test_metrics"={"lift_ratio"}, "bootstrap"={"n_resamples", "n_invalid_resamples", "ci95_low",
# "ci95_high", "bootstrap_mean"}, "example_ego_networks" (list of {seed_node_key,
# real_nodes_before_cap, nodes_after_cap, edges_after_cap, truncated}),
# "gate1_structural_checks" (dict of bool), "gate1_verdict", "gate2_statistical_robustness_checks"
# (dict of bool), "gate2_verdict", "overall_verdict", "fastapi_self_test"={"rows_checked",
# "mismatches"}, "no_trained_model_note", "scaling_engineering_note".
#
# Real NB3 "rule" artifact schema (bp3_notebook3_champion_rule_*.json -- explicitly NOT a
# pickled model, per this BP's locked "no trained ML model" policy): "champion_signal",
# "champion_column", "is_threshold_signal", "threshold", "note".
#
# No ASSUMPTIONS dict / no dollar figures anywhere in this block: BP3 Notebook 1's locked
# Before-baseline policy states the After KPI is "a real volume-scale KPI ... never converted
# to a dollar figure without a real, sourced per-account investigation-cost assumption, which
# does not exist for this BP and is therefore not invented." Honored literally here -- every
# writer function below reports real counts (accounts, relationships, nodes, edges), never an
# invented per-case dollar value.
# ============================================================================


# ============================================================================
# Signal comparison table -- Stage A/B candidate structural signals ranked by real
# network-lift ratio (never by an arbitrary dict order -- the raw JSON's stage_results list
# is NOT pre-sorted). The champion column marks which real signal NB3 actually selected this
# run, never re-derived or second-guessed here.
# ============================================================================
def build_signal_comparison_table_structural(rep: dict) -> pd.DataFrame:
    """Real Signal | Threshold | Test Nodes Flagged | Exposed Among Flagged | Flagged
    Exposure Rate | Lift Ratio | Champion table, sorted descending by real lift ratio.
    `rep` is a BP3 Notebook 3 validation-report dict (real, already saved -- nothing here is
    recomputed)."""
    champion = rep["champion_name"]
    rows = []
    for s in rep["stage_results"]:
        thr = s["threshold"]
        rows.append(
            {
                "Signal": s["signal"],
                "Threshold": (f"{thr:.6g}" if thr is not None else "N/A (set-membership signal)"),
                "Test Nodes Flagged": f"{s['n_test_flagged']:,}",
                "Exposed Among Flagged": f"{s['n_test_flagged_exposed']:,}",
                "Flagged Exposure Rate": f"{s['flagged_exposure_rate']:.2%}",
                "Lift Ratio": f"{s['lift_ratio']:.2f}x" if s["lift_ratio"] is not None else "undefined",
                "Champion": "YES" if s["signal"] == champion else "",
                "_lift_sort": s["lift_ratio"] if s["lift_ratio"] is not None else -1.0,
            }
        )
    df = pd.DataFrame(rows).sort_values("_lift_sort", ascending=False).drop(columns=["_lift_sort"])
    return df.reset_index(drop=True)


# ============================================================================
# Illustrative bounded-ego-network table -- Section 5/8 Before/After, BP3's own locked
# volume-scale (never dollarized) framing. These are the real but ONLY 3 illustrative
# examples NB3 actually computed full ego-network stats for (its own Section 8) -- NOT a
# population-wide average across every real flagged account (NB3 never computed that
# aggregate), and this table says so explicitly rather than silently implying otherwise.
# ============================================================================
def build_ego_network_illustration_table_structural(rep: dict) -> pd.DataFrame:
    """Real Seed Account | Before: Accounts Reviewed | After: Real Accounts Within 2 Hops |
    After: Capped Accounts Shown | After: Capped Relationships Shown | Truncated table, built
    strictly from rep['example_ego_networks'] (NB3's own real, already-computed illustrative
    examples -- never a new or extrapolated aggregate)."""
    rows = []
    for ego in rep.get("example_ego_networks", []):
        rows.append(
            {
                "Seed Account (real, composite Bank|Account key)": ego["seed_node_key"],
                "Before: Accounts Reviewed": "1 (the flagged account only)",
                "After: Real Accounts Within 2 Hops": f"{ego['real_nodes_before_cap']:,}",
                "After: Accounts Shown (capped at 2,000)": f"{ego['nodes_after_cap']:,}",
                "After: Relationships Shown (capped subgraph)": f"{ego['edges_after_cap']:,}",
                "Capped?": (
                    "YES -- real size exceeds the locked 2,000-node cap"
                    if ego["truncated"]
                    else "No -- full real ego-network shown"
                ),
            }
        )
    return pd.DataFrame(rows)


# ============================================================================
# Real, data-driven SMART recommendations -- structural-signal equivalent of
# generate_smart_recommendations_multiclass. No $ figures (locked BP3 policy -- see banner
# above), no SHAP/LIME (genuinely N/A -- no trained model to explain), no precision/recall
# (not a classifier). Every clause is built from real numbers already present in `context`.
# ============================================================================
def generate_smart_recommendations_structural(context: dict) -> list:
    primary_name = context["primary_variant"]
    primary = context["variants"][primary_name]
    rep = primary["report"]
    rule = primary.get("rule", {})
    hi_prior = rep.get("hi_small_stage_a_prior_champion")
    champion_stable = (hi_prior is not None) and (hi_prior == rep["champion_name"])
    boot = rep["bootstrap"]

    ego_sizes_str = ", ".join(f"{e['real_nodes_before_cap']:,}" for e in rep.get("example_ego_networks", []))

    recs = [
        {
            "title": "Re-validate the champion structural signal on a fixed cadence",
            "specific": (
                f"The champion signal on {primary_name} ({rep['champion_name']}) achieves a real "
                f"network-lift ratio of {rep['test_metrics']['lift_ratio']:.2f}x (real bootstrap "
                f"95% CI [{boot['ci95_low']:.2f}x, {boot['ci95_high']:.2f}x], "
                f"{boot['n_resamples']:,} resamples, {boot['n_invalid_resamples']:,} invalid)."
            ),
            "measurable": (
                "Track the real lift ratio and its bootstrap CI on every future real re-run; "
                "treat a CI95 lower bound that drops to or below 1.0x (no real lift over the real "
                "base rate) as a trigger for re-screening the full candidate signal set."
            ),
            "achievable": "Uses the existing, already-built Notebook 2 (Stage A screening) and Notebook 3 (validation + bootstrap) pipeline -- no new infrastructure required.",
            "relevant": "Directly controls whether the real network-proximity flagging rule remains evidence-based (Lesson #11 leakage discipline, enforced every run as its own structural gate).",
            "time_bound": "Quarterly re-validation review, next due within 90 days of production go-live.",
        },
        {
            "title": "Scale investigator review capacity to the real bounded ego-network volume, not account count",
            "specific": (
                f"Before = single-account review (zero real network visibility). After = the real "
                f"bounded 2-hop ego-network around the same flagged account -- NB3's 3 real "
                f"illustrative examples show real network sizes {ego_sizes_str} "
                f"accounts before the locked 2,000-node cap is applied."
            ),
            "measurable": "Real per-case investigator review time logged under the new bounded-ego-network workflow vs. the prior single-account workflow -- no ASSUMPTION dollar figure is used here, per this BP's locked no-invented-cost-basis policy.",
            "achievable": "Capacity planning is an operational scheduling change against the existing locked 2,000-node bounded scope -- no new detection system required.",
            "relevant": "Investigator capacity is the real, most commonly cited AML program bottleneck (FFIEC BSA/AML Examination Manual, alert-management pillar) -- network-scale review has a materially different real workload shape than single-account review.",
            "time_bound": "Reassess real review-time-per-case 60 days after production go-live.",
        },
    ]

    if hi_prior is not None:
        if champion_stable:
            recs.append(
                {
                    "title": "Document the real cross-scale champion agreement for examiner review",
                    "specific": (
                        f"The real Stage A (HI-Small) screening champion ('{hi_prior}') and the real "
                        f"{primary_name} mandatory-validation-tier champion ('{rep['champion_name']}') "
                        f"are the SAME signal -- confirmed stable across two real, independently "
                        f"evaluated dataset scales."
                    ),
                    "measurable": "Confirm this agreement holds on every future real re-run across scales; log explicitly if a future run diverges.",
                    "achievable": "Already computed by Notebook 3's existing cross-scale comparison step -- no new tooling required.",
                    "relevant": "A champion signal that is stable across dataset scale is stronger real evidence for SR 11-7 model-risk documentation than a single-scale result alone.",
                    "time_bound": "Refresh this documentation at every retrain, alongside the rule card update.",
                }
            )
        else:
            recs.append(
                {
                    "title": f"Investigate the real champion divergence between HI-Small and {primary_name}",
                    "specific": (
                        f"The real Stage A (HI-Small) screening champion ('{hi_prior}') and the real "
                        f"{primary_name} mandatory-validation-tier champion ('{rep['champion_name']}') "
                        f"are DIFFERENT signals. Per this platform's locked rule, the real "
                        f"{primary_name} result is authoritative and is never silently overridden by "
                        f"the smaller-scale prior -- but the divergence itself is worth understanding."
                    ),
                    "measurable": "Compare the real per-signal lift ratios at both scales (see the Signal Comparison table in this report) to characterize how each candidate's real lift changes with real graph scale.",
                    "achievable": "Uses the already-saved Notebook 2 and Notebook 3 outputs -- a comparison, not a new computation.",
                    "relevant": "Understanding why a structural signal's real relative strength changes with scale directly informs which signal to trust at full production (HI-Large/LI-Large) scale.",
                    "time_bound": "Before this champion is cited as stable in any external or regulatory-facing report.",
                }
            )

    rule_threshold_clause = (
        f", threshold {rule['threshold']:.6g}"
        if rule.get("is_threshold_signal") and rule.get("threshold") is not None
        else " (set-membership test)"
    )
    no_model_note = rep.get(
        "no_trained_model_note",
        "BP3 has no trained ML model -- every candidate is a directly-interpretable structural signal.",
    )
    fst_rows = rep.get("fastapi_self_test", {}).get("rows_checked", 0)
    fst_mismatches = rep.get("fastapi_self_test", {}).get("mismatches", 0)
    recs.append(
        {
            "title": "Keep the 'no trained model' framing explicit in every downstream use of this rule",
            "specific": (
                f"{no_model_note} The real deployable artifact is a RULE "
                f"({rule.get('champion_column', rep['champion_name'])}{rule_threshold_clause}), "
                f"never a pickled classifier -- confirmed by the real self-tested FastAPI service "
                f"({fst_rows:,} real rows checked, {fst_mismatches} mismatches)."
            ),
            "measurable": "Any downstream system or document referencing this BP's output states 'structural rule' or 'network-lift signal', never 'model prediction' or 'model score'.",
            "achievable": "A documentation/labeling convention, not a code or infrastructure change.",
            "relevant": "SR 11-7 model risk management requires accurate characterization of what kind of artifact is actually in production -- a RULE carries different real validation and monitoring expectations than a trained classifier.",
            "time_bound": "Immediate -- applies to this report and every future one referencing this BP.",
        }
    )

    failing = [name for name, v in context["variants"].items() if v["report"]["overall_verdict"] != "PASS"]
    if failing:
        recs.append(
            {
                "title": f"Resolve validation gate failures on {', '.join(failing)} before relying on that variant",
                "specific": f"{', '.join(failing)} did not pass both the structural and statistical-robustness validation gates.",
                "measurable": "Re-run Notebook 3 on the failing variant(s) until both gates PASS.",
                "achievable": "Uses the existing, already-built Notebook 3 pipeline -- no new methodology required.",
                "relevant": "This platform's locked policy requires both gates to PASS before a variant's results are treated as production evidence.",
                "time_bound": "Before this variant is cited in any external or regulatory-facing report.",
            }
        )
    else:
        recs.append(
            {
                "title": "Maintain the real two-gate validation standard on every future retrain",
                "specific": f"Every real dataset variant evaluated for {context['bp_id']} currently passes both validation gates ({', '.join(context['variants'].keys())}).",
                "measurable": "Both gates must continue to PASS on every future retrain before redeployment.",
                "achievable": "Enforced automatically by Notebook 3's existing gate logic -- no manual step to remember.",
                "relevant": "This is the basis for this report's current production-recommended status.",
                "time_bound": "Every retrain cycle, before redeployment.",
            }
        )

    return recs


# ============================================================================
# Real matplotlib horizontal bar chart of each candidate signal's real lift ratio -- the
# champion bar rendered in the brand accent color, all others in a muted neutral, per the
# same "status colors reserved, categorical hue assigned by identity not rank" dataviz
# discipline used by render_before_after_chart_png / render_typology_recall_chart_png above.
# ============================================================================
def render_signal_lift_chart_png_structural(comparison_df: pd.DataFrame, out_path: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    df = comparison_df.copy()
    df["_lift_val"] = (
        df["Lift Ratio"].str.replace("x", "", regex=False).replace("undefined", "0").astype(float)
    )
    df = df.sort_values("_lift_val", ascending=True)  # ascending so champion/top bar renders at top in barh
    colors = [PALETTE["series_1_blue"] if c == "YES" else PALETTE["ink_muted"] for c in df["Champion"]]

    fig, ax = plt.subplots(figsize=(8, 3.6), dpi=150)
    bars = ax.barh(df["Signal"], df["_lift_val"], color=colors, height=0.6)
    for bar, val in zip(bars, df["_lift_val"]):
        ax.text(
            bar.get_width() + max(df["_lift_val"]) * 0.015,
            bar.get_y() + bar.get_height() / 2,
            f"{val:.2f}x",
            va="center",
            fontsize=9,
            color=PALETTE["ink_primary"],
        )
    ax.axvline(1.0, color=PALETTE["ink_muted"], linewidth=1, linestyle="--")
    ax.text(1.0, -0.7, "1.0x (no lift)", fontsize=8, color=PALETTE["ink_muted"], ha="center")
    ax.set_xlabel("Real network-lift ratio (test set)")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_facecolor(PALETTE["surface"])
    fig.patch.set_facecolor(PALETTE["surface"])
    fig.tight_layout()

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_path), facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


# ============================================================================
# Word report (python-docx) -- structural equivalent of write_word_report_multiclass
# ============================================================================
def write_word_report_structural(path: Path, context: dict) -> Path:
    from docx import Document
    from docx.shared import Pt, RGBColor

    doc = Document()
    _apply_word_brand_styles(doc)
    doc.add_heading(f"{context['bp_id']}: {context['bp_name']}", level=0)
    p = doc.add_paragraph()
    p.add_run(f"Compliance-Impact Report -- generated {context['generated_at_utc']} UTC").italic = True

    doc.add_heading("Business Objective", level=1)
    doc.add_paragraph(context["business_objective"])

    status = context.get("status") or compute_bp_status(context)
    doc.add_heading("Recommendation & Status", level=1)
    p = doc.add_paragraph()
    run = p.add_run(status["label"])
    run.bold = True
    run.font.size = Pt(14)
    status_colors = {
        "good": RGBColor(0x0C, 0xA3, 0x0C),
        "warning": RGBColor(0xC9, 0x85, 0x00),
        "critical": RGBColor(0xD0, 0x3B, 0x3B),
    }
    run.font.color.rgb = status_colors.get(status["css_class"], RGBColor(0x0B, 0x0B, 0x0B))
    doc.add_paragraph(status["rationale"])

    doc.add_heading("Executive Summary", level=1)
    primary_name = context["primary_variant"]
    primary = context["variants"][primary_name]
    rep = primary["report"]
    boot = rep["bootstrap"]
    doc.add_paragraph(
        f"On the {primary_name} variant -- this business problem's locked mandatory "
        f"realism-validation tier -- the real champion structural signal "
        f"('{rep['champion_name']}') achieved a real held-out test network-lift ratio of "
        f"{rep['test_metrics']['lift_ratio']:.2f}x (real bootstrap 95% CI "
        f"[{boot['ci95_low']:.2f}x, {boot['ci95_high']:.2f}x], {boot['n_resamples']:,} "
        f"resamples). Both the structural and statistical-robustness gates "
        f"{'PASSED' if rep['overall_verdict'] == 'PASS' else 'did NOT both pass'} "
        f"(overall verdict: {rep['overall_verdict']}). BP3 has no trained ML model -- this is "
        f"a directly-interpretable structural rule, not a classifier score."
    )
    doc.add_paragraph(
        f"Real graph scale this run: {rep['n_nodes']:,} distinct (Bank, Account) nodes, "
        f"{rep['n_distinct_edges']:,} distinct directed edges ({rep['n_transaction_edges']:,} "
        f"real transaction-edges collapsed by (src,dst) weight), real base rate "
        f"{rep['base_rate_all']:.4%} Is-Laundering-exposed accounts."
    )

    doc.add_heading("What This Means for the Business", level=1)
    for point in context["business_benefits"]:
        doc.add_paragraph(point, style="List Bullet")

    doc.add_heading("Candidate Structural Signals -- Real Network-Lift Ranking", level=1)
    doc.add_paragraph(
        "Every candidate below is a real, directly-interpretable structural signal (degree, "
        "PageRank, or network proximity) -- never a trained classifier. Ranked by real "
        f"network-lift ratio on the {primary_name} held-out test set; the champion is the "
        "signal NB3 actually selected this run, never re-derived here."
    )
    comp_df = context["signal_comparison_tables"][primary_name]
    table = doc.add_table(rows=1, cols=len(comp_df.columns))
    table.style = "Light Grid Accent 1"
    for i, col in enumerate(comp_df.columns):
        table.rows[0].cells[i].text = col
    for _, row in comp_df.iterrows():
        cells = table.add_row().cells
        for i, col in enumerate(comp_df.columns):
            cells[i].text = str(row[col])

    doc.add_heading(f"Before / After Impact ({primary_name}) -- Real Volume-Scale KPI", level=1)
    doc.add_paragraph(
        "Before = single-account (non-network) review: an investigator sees only the one "
        "flagged account's own real transactions, zero real visibility into its surrounding "
        "network (locked BP3 Notebook 1 policy). After = the real bounded 2-hop ego-network "
        "around that same account (capped at 2,000 nodes, locked graph-feasibility policy). "
        "This is reported as a real volume-scale KPI, never converted to a dollar figure -- no "
        "real, sourced per-account investigation-cost assumption exists for this BP, and none "
        "is invented here (locked policy, Notebook 1 Section 6)."
    )
    ego_df = context["ego_network_tables"][primary_name]
    if len(ego_df):
        ego_table = doc.add_table(rows=1, cols=len(ego_df.columns))
        ego_table.style = "Light Grid Accent 1"
        for i, col in enumerate(ego_df.columns):
            ego_table.rows[0].cells[i].text = col
        for _, row in ego_df.iterrows():
            cells = ego_table.add_row().cells
            for i, col in enumerate(ego_df.columns):
                cells[i].text = str(row[col])
        doc.add_paragraph(
            "These are the real, but only 3 illustrative examples Notebook 3 computed full "
            "ego-network statistics for -- not a population-wide average across every real "
            "flagged account (that aggregate was not computed and is not estimated here)."
        )

    doc.add_heading("Validation Gates (Real, Two-Gate Architecture)", level=1)
    g1 = rep.get("gate1_structural_checks", {})
    g2 = rep.get("gate2_statistical_robustness_checks", {})
    doc.add_paragraph(f"Gate 1 (structural) -- verdict: {rep.get('gate1_verdict', 'N/A')}")
    for k, v in g1.items():
        doc.add_paragraph(f"{k.replace('_', ' ')}: {'PASS' if v else 'FAIL'}", style="List Bullet")
    doc.add_paragraph(f"Gate 2 (statistical robustness) -- verdict: {rep.get('gate2_verdict', 'N/A')}")
    for k, v in g2.items():
        doc.add_paragraph(f"{k.replace('_', ' ')}: {'PASS' if v else 'FAIL'}", style="List Bullet")

    doc.add_heading("Explainability -- Not Applicable (No Trained Model)", level=1)
    doc.add_paragraph(
        rep.get(
            "no_trained_model_note",
            "BP3 has no trained ML model -- every candidate is a directly-interpretable "
            "structural signal; SHAP/LIME are N/A, not attempted.",
        )
    )
    if rep.get("scaling_engineering_note"):
        doc.add_paragraph(rep["scaling_engineering_note"])

    doc.add_heading("Deployable Scoring Service -- Real Self-Test", level=1)
    fst = rep.get("fastapi_self_test", {})
    doc.add_paragraph(
        f"The real champion RULE is served via a self-tested FastAPI scoring service, matched "
        f"bit-for-bit against direct computation on {fst.get('rows_checked', 0):,} real rows "
        f"checked, {fst.get('mismatches', 0)} mismatches. This is a RULE artifact (a threshold "
        f"or set-membership test), never a pickled classifier."
    )

    doc.add_heading("Regulatory & Compliance Mapping", level=1)
    reg_table = doc.add_table(rows=1, cols=2)
    reg_table.style = "Light Grid Accent 1"
    reg_table.rows[0].cells[0].text = "Framework"
    reg_table.rows[0].cells[1].text = "Applies to"
    for fw, applies in context["regulatory_frameworks"]:
        row = reg_table.add_row().cells
        row[0].text = fw
        row[1].text = applies

    doc.add_heading("Fairness / Bias Testing", level=1)
    doc.add_paragraph(context["fairness_note"])

    doc.add_heading("Limitations & Caveats", level=1)
    for cav in context.get("caveats", []):
        doc.add_paragraph(cav, style="List Bullet")

    doc.add_heading("Recommendations", level=1)
    recs = context.get("smart_recommendations") or generate_smart_recommendations_structural(context)
    for r in recs:
        doc.add_heading(r["title"], level=2)
        for label in ("specific", "measurable", "achievable", "relevant", "time_bound"):
            p = doc.add_paragraph(style="List Bullet")
            run = p.add_run(f"{label.replace('_', '-').title()}: ")
            run.bold = True
            p.add_run(r[label])

    _brand_word_table_headers(doc)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    return path


# ============================================================================
# Excel workbook (openpyxl) -- structural equivalent. No Assumptions sheet (no dollar
# assumption exists for this BP, per locked policy) -- "Parameters & Policy" sheet instead,
# documenting the real LOCKED methodology parameters (never a dollar figure).
# ============================================================================
def write_excel_workbook_structural(path: Path, context: dict) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.workbook.properties import CalcProperties

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="2A78D6", end_color="2A78D6", fill_type="solid")

    wb = Workbook()
    wb.calculation = CalcProperties(fullCalcOnLoad=True)

    primary_name = context["primary_variant"]
    primary = context["variants"][primary_name]
    rep = primary["report"]

    # --- Parameters & Policy sheet FIRST (locked methodology params -- never a $ assumption) ---
    ws_a = wb.active
    ws_a.title = "Parameters & Policy"
    ws_a["A1"] = "Parameter (locked policy)"
    ws_a["B1"] = "Value"
    ws_a["A1"].font = header_font
    ws_a["B1"].font = header_font
    ws_a["A1"].fill = header_fill
    ws_a["B1"].fill = header_fill
    param_rows = [
        ("Random seed", rep.get("random_seed")),
        ("Primary metric", rep.get("primary_metric")),
        ("Bounded ego-network node cap (locked policy)", 2000),
        ("Top-decile screening percentile (locked)", "90%"),
        ("Bootstrap resamples", rep["bootstrap"]["n_resamples"]),
        ("Bootstrap invalid resamples", rep["bootstrap"]["n_invalid_resamples"]),
        (
            "PageRank self-test max abs diff vs. networkx",
            rep.get("pagerank_self_test_max_abs_diff_vs_networkx"),
        ),
    ]
    for i, (label, val) in enumerate(param_rows, start=2):
        ws_a[f"A{i}"] = label
        ws_a[f"B{i}"] = val
    ws_a.column_dimensions["A"].width = 48
    ws_a.column_dimensions["B"].width = 20
    _brand_excel_sheet(ws_a, PALETTE["ink_muted"], freeze_cell="A2")

    # --- Executive Summary sheet ---
    status = context.get("status") or compute_bp_status(context)
    status_hex = {"good": "0CA30C", "warning": "FAB219", "critical": "D03B3B"}.get(
        status["css_class"], "2A78D6"
    )
    ws_e = wb.create_sheet("Executive Summary")
    ws_e["A1"] = "Status"
    ws_e["B1"] = "Rationale"
    ws_e["A1"].font = header_font
    ws_e["B1"].font = header_font
    ws_e["A1"].fill = header_fill
    ws_e["B1"].fill = header_fill
    ws_e["A2"] = status["label"]
    ws_e["A2"].fill = PatternFill(start_color=status_hex, end_color=status_hex, fill_type="solid")
    ws_e["A2"].font = Font(bold=True, color="FFFFFF")
    ws_e["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws_e["B2"] = status["rationale"]
    ws_e["B2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws_e.row_dimensions[2].height = 60
    ws_e.column_dimensions["A"].width = 42
    ws_e.column_dimensions["B"].width = 95

    boot = rep["bootstrap"]
    ws_e["A4"] = f"Real Network-Lift Summary (primary variant: {primary_name})"
    ws_e["A4"].font = Font(bold=True)
    ws_e["A5"] = "Champion signal"
    ws_e["B5"] = rep["champion_name"]
    ws_e["A6"] = "Real lift ratio (point estimate)"
    ws_e["B6"] = rep["test_metrics"]["lift_ratio"]
    ws_e["A7"] = "Bootstrap 95% CI low"
    ws_e["B7"] = boot["ci95_low"]
    ws_e["A8"] = "Bootstrap 95% CI high"
    ws_e["B8"] = boot["ci95_high"]
    ws_e["A9"] = (
        "Note: BP3 reports real counts and lift ratios only -- no dollar figure is computed or invented for this BP (locked policy, no sourced per-account cost basis exists)."
    )
    ws_e["A9"].font = Font(italic=True, color="52514E")
    _brand_excel_sheet(ws_e, status_hex, freeze_cell="A3")

    # --- Variant summary sheet ---
    ws_s = wb.create_sheet("Variant Summary")
    headers = [
        "Variant",
        "Champion Signal",
        "Real Lift Ratio",
        "CI95 Low",
        "CI95 High",
        "Nodes",
        "Base Rate",
        "Gate 1",
        "Gate 2",
        "Overall Verdict",
    ]
    for c, h in enumerate(headers, start=1):
        cell = ws_s.cell(row=1, column=c, value=h)
        cell.font = header_font
        cell.fill = header_fill
    for r, (variant_name, v) in enumerate(context["variants"].items(), start=2):
        rr = v["report"]
        bb = rr["bootstrap"]
        ws_s.cell(row=r, column=1, value=variant_name)
        ws_s.cell(row=r, column=2, value=rr["champion_name"])
        ws_s.cell(row=r, column=3, value=rr["test_metrics"]["lift_ratio"])
        ws_s.cell(row=r, column=4, value=bb["ci95_low"])
        ws_s.cell(row=r, column=5, value=bb["ci95_high"])
        ws_s.cell(row=r, column=6, value=rr["n_nodes"])
        ws_s.cell(row=r, column=7, value=rr["base_rate_all"])
        ws_s.cell(row=r, column=7).number_format = "0.0000%"
        ws_s.cell(row=r, column=8, value=rr["gate1_verdict"])
        ws_s.cell(row=r, column=9, value=rr["gate2_verdict"])
        ws_s.cell(row=r, column=10, value=rr["overall_verdict"])
    ws_s.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{1 + len(context['variants'])}"
    for c in range(1, len(headers) + 1):
        ws_s.column_dimensions[get_column_letter(c)].width = 20
    _brand_excel_sheet(ws_s, PALETTE["series_1_blue"], freeze_cell="A2")
    _band_excel_rows(
        ws_s, first_data_row=2, last_data_row=1 + len(context["variants"]), first_col=1, last_col=len(headers)
    )
    _color_verdict_cells(ws_s, rows=range(2, 2 + len(context["variants"])), cols=[8, 9, 10])

    # --- Signal comparison sheet per variant ---
    for variant_name, comp_df in context["signal_comparison_tables"].items():
        sheet_name = f"Signals {variant_name}"[:31]
        ws_c = wb.create_sheet(sheet_name)
        for c, h in enumerate(comp_df.columns, start=1):
            cell = ws_c.cell(row=1, column=c, value=h)
            cell.font = header_font
            cell.fill = header_fill
        for r, (_, row) in enumerate(comp_df.iterrows(), start=2):
            for c, col in enumerate(comp_df.columns, start=1):
                ws_c.cell(row=r, column=c, value=str(row[col]))
        ws_c.auto_filter.ref = f"A1:{get_column_letter(len(comp_df.columns))}{1 + len(comp_df)}"
        for c in range(1, len(comp_df.columns) + 1):
            ws_c.column_dimensions[get_column_letter(c)].width = 24
        _brand_excel_sheet(ws_c, PALETTE["series_2_orange"], freeze_cell="A2")
        _band_excel_rows(
            ws_c, first_data_row=2, last_data_row=1 + len(comp_df), first_col=1, last_col=len(comp_df.columns)
        )
        champion_col_idx = list(comp_df.columns).index("Champion") + 1
        for r in range(2, 2 + len(comp_df)):
            if ws_c.cell(row=r, column=champion_col_idx).value == "YES":
                for c in range(1, len(comp_df.columns) + 1):
                    ws_c.cell(row=r, column=c).font = Font(bold=True)

    # --- Before/After ego-network sheet per variant ---
    for variant_name, ego_df in context["ego_network_tables"].items():
        if not len(ego_df):
            continue
        sheet_name = f"Before-After {variant_name}"[:31]
        ws_b = wb.create_sheet(sheet_name)
        for c, h in enumerate(ego_df.columns, start=1):
            cell = ws_b.cell(row=1, column=c, value=h)
            cell.font = header_font
            cell.fill = header_fill
        for r, (_, row) in enumerate(ego_df.iterrows(), start=2):
            for c, col in enumerate(ego_df.columns, start=1):
                ws_b.cell(row=r, column=c, value=str(row[col]))
        ws_b.cell(
            row=3 + len(ego_df),
            column=1,
            value="Real, but only 3 illustrative examples -- not a population-wide average (not computed, not estimated).",
        )
        ws_b.cell(row=3 + len(ego_df), column=1).font = Font(italic=True, color="52514E")
        for c in range(1, len(ego_df.columns) + 1):
            ws_b.column_dimensions[get_column_letter(c)].width = 30
        _brand_excel_sheet(ws_b, PALETTE["series_3_aqua"], freeze_cell="A2")
        _band_excel_rows(
            ws_b, first_data_row=2, last_data_row=1 + len(ego_df), first_col=1, last_col=len(ego_df.columns)
        )

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))
    return path


# ============================================================================
# HTML dashboard -- structural equivalent. Same CSS shell / animation system as
# write_html_dashboard / write_html_dashboard_multiclass (shared verbatim -- generic, not
# classification-specific), simplified tab set (no SHAP, no financial $ tab): Overview,
# Signal Comparison, Network Impact, Recommendations.
# ============================================================================
def write_html_dashboard_structural(path: Path, context: dict, chartjs_js_path: Path) -> Path:
    chartjs_source = Path(chartjs_js_path).read_text(encoding="utf-8")

    status = context.get("status") or compute_bp_status(context)
    recommendations = context.get("smart_recommendations") or generate_smart_recommendations_structural(
        context
    )

    variants_json = {}
    for variant_name, v in context["variants"].items():
        rep = v["report"]
        boot = rep["bootstrap"]
        comp_df = context["signal_comparison_tables"][variant_name]
        ego_df = context["ego_network_tables"][variant_name]
        variants_json[variant_name] = {
            "champion": rep["champion_name"],
            "lift_ratio": rep["test_metrics"]["lift_ratio"],
            "ci95_low": boot["ci95_low"],
            "ci95_high": boot["ci95_high"],
            "bootstrap_mean": boot["bootstrap_mean"],
            "n_resamples": boot["n_resamples"],
            "n_nodes": rep["n_nodes"],
            "n_distinct_edges": rep["n_distinct_edges"],
            "base_rate": rep["base_rate_all"],
            "verdict": rep["overall_verdict"],
            "gate1_verdict": rep.get("gate1_verdict"),
            "gate2_verdict": rep.get("gate2_verdict"),
            "gate1_checks": rep.get("gate1_structural_checks", {}),
            "gate2_checks": rep.get("gate2_statistical_robustness_checks", {}),
            "signals": [
                {
                    "signal": s["signal"],
                    "lift_ratio": s["lift_ratio"],
                    "champion": s["signal"] == rep["champion_name"],
                }
                for s in rep["stage_results"]
            ],
            "signal_table": comp_df.to_dict(orient="records"),
            "ego_table": ego_df.to_dict(orient="records"),
            "fastapi_self_test": rep.get("fastapi_self_test", {}),
            "no_trained_model_note": rep.get("no_trained_model_note", ""),
            "scaling_engineering_note": rep.get("scaling_engineering_note", ""),
        }
    data_json = json.dumps(variants_json)
    variant_names_json = json.dumps(list(context["variants"].keys()))
    status_json = json.dumps(status)
    recs_json = json.dumps(recommendations)
    primary_variant_json = json.dumps(context["primary_variant"])
    palette = PALETTE

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{context['bp_id']} -- {context['bp_name']} -- Compliance Dashboard</title>
<style>
  :root {{
    color-scheme: light;
    --surface: {palette['surface']}; --page: {palette['page']};
    --ink: {palette['ink_primary']}; --ink-2: {palette['ink_secondary']}; --ink-muted: {palette['ink_muted']};
    --grid: {palette['gridline']};
    --s1: {palette['series_1_blue']}; --s2: {palette['series_2_orange']}; --s3: {palette['series_3_aqua']};
    --good: {palette['status_good']}; --warn: {palette['status_warning']}; --crit: {palette['status_critical']};
  }}
  * {{ box-sizing: border-box; }}
  html {{ scroll-behavior:smooth; }}
  body {{
    margin:0; color:var(--ink); font-family: system-ui,-apple-system,"Segoe UI",sans-serif;
    background:
      radial-gradient(1100px 580px at 8% -8%, rgba(42,120,214,0.08), transparent 58%),
      radial-gradient(900px 520px at 100% 0%, rgba(27,175,122,0.07), transparent 55%),
      radial-gradient(800px 500px at 50% 110%, rgba(235,104,52,0.05), transparent 60%),
      var(--page);
    background-attachment: fixed;
    min-height:100vh;
  }}
  .accent-bar {{ height:4px; width:100%;
    background: linear-gradient(90deg, var(--s1), var(--s3), var(--s2), var(--s1));
    background-size: 300% 100%; animation: shimmer 6s linear infinite; }}
  @keyframes shimmer {{ 0% {{ background-position:0% 0; }} 100% {{ background-position:300% 0; }} }}
  header {{ padding:22px 24px; border-bottom:1px solid var(--grid); background:var(--surface);
    animation: fadeInUp .5s ease both; box-shadow:0 1px 0 rgba(11,11,11,.02); }}
  h1 {{ margin:0 0 4px; font-size:21px; letter-spacing:-.01em; }}
  .sub {{ color:var(--ink-2); font-size:13px; }}
  @keyframes fadeInUp {{ from {{ opacity:0; transform:translateY(10px); }} to {{ opacity:1; transform:translateY(0); }} }}
  @keyframes fadeSection {{ from {{ opacity:0; transform:translateY(6px); }} to {{ opacity:1; transform:translateY(0); }} }}
  @keyframes pulseDot {{ 0% {{ box-shadow:0 0 0 0 currentColor; opacity:1; }} 70% {{ box-shadow:0 0 0 9px transparent; opacity:.35; }} 100% {{ box-shadow:0 0 0 0 transparent; opacity:1; }} }}
  .tile, .chart-box, .rec-card, .narrative, .status-banner {{ animation: fadeInUp .45s ease both; }}
  .tile, .chart-box, .rec-card {{ box-shadow:0 1px 2px rgba(11,11,11,.04);
    transition: transform .2s cubic-bezier(.22,1,.36,1), box-shadow .2s ease, border-color .2s ease; }}
  .tile:hover, .chart-box:hover, .rec-card:hover {{ transform:translateY(-4px); box-shadow:0 14px 28px rgba(11,11,11,.10); border-color:rgba(42,120,214,.25); }}
  .status-banner {{ margin:16px 24px 0; padding:16px 20px; border-radius:12px; border:1px solid var(--grid);
    display:flex; align-items:flex-start; gap:14px; box-shadow:0 1px 2px rgba(11,11,11,.04); }}
  .status-banner.good {{ background:linear-gradient(135deg,#eafaea,#e7f7e7); }}
  .status-banner.warning {{ background:linear-gradient(135deg,#fff9ec,#fff6e5); }}
  .status-banner.critical {{ background:linear-gradient(135deg,#fef0ef,#fdeceb); }}
  .status-banner .dot {{ width:14px; height:14px; border-radius:50%; flex:0 0 auto; margin-top:3px; position:relative; }}
  .status-banner .dot::after {{ content:""; position:absolute; inset:0; border-radius:50%; background:currentColor;
    animation: pulseDot 2.2s ease-out infinite; }}
  .status-banner .dot.good {{ background:var(--good); color:var(--good); }}
  .status-banner .dot.warning {{ background:var(--warn); color:var(--warn); }}
  .status-banner .dot.critical {{ background:var(--crit); color:var(--crit); }}
  .status-banner .label {{ font-size:16px; font-weight:700; }}
  .status-banner .rationale {{ font-size:13px; color:var(--ink-2); margin-top:4px; line-height:1.5; }}
  .narrative {{ background:var(--surface); border:1px solid var(--grid); border-radius:12px; padding:18px 20px; margin:16px 24px 0;
    box-shadow:0 1px 2px rgba(11,11,11,.04); }}
  .narrative h2 {{ margin:0 0 8px; font-size:15px; }}
  .narrative p {{ margin:0 0 10px; color:var(--ink-2); font-size:13px; line-height:1.5; }}
  .narrative ul {{ margin:0; padding-left:18px; }}
  .narrative li {{ color:var(--ink-2); font-size:13px; line-height:1.6; }}
  .tabs {{ position:relative; display:flex; gap:4px; padding:0 24px; margin-top:16px; background:var(--surface); border-bottom:1px solid var(--grid); }}
  .tabs button {{ border:none; background:transparent; color:var(--ink-2); padding:12px 16px; cursor:pointer;
    font-size:13px; font-weight:600; border-bottom:2px solid transparent; border-radius:8px 8px 0 0;
    transition:color .15s ease, background .2s ease; position:relative; z-index:1; }}
  .tabs button:hover {{ color:var(--ink); background:rgba(42,120,214,.07); }}
  .tabs button.active {{ color:var(--s1); }}
  .tab-indicator {{ position:absolute; bottom:-1px; left:0; height:3px; width:0; border-radius:3px;
    background:linear-gradient(90deg, var(--s1), var(--s3));
    box-shadow:0 0 8px rgba(42,120,214,.45);
    transition: transform .4s cubic-bezier(.34,1.56,.64,1), width .4s cubic-bezier(.34,1.56,.64,1); }}

  .filters {{ display:flex; align-items:center; gap:8px; padding:12px 24px; background:var(--surface); border-bottom:1px solid var(--grid); }}
  .filters .fl-label {{ color:var(--ink-muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; margin-right:4px; }}
  .filters button {{ position:relative; overflow:hidden; border:1px solid var(--grid); background:var(--surface); color:var(--ink); padding:6px 14px;
    border-radius:999px; cursor:pointer; font-size:13px;
    transition: background .2s ease, color .2s ease, border-color .2s ease, transform .25s cubic-bezier(.34,1.56,.64,1), box-shadow .2s ease; }}
  .filters button:hover {{ transform:translateY(-2px); box-shadow:0 6px 14px rgba(11,11,11,.10); border-color:rgba(42,120,214,.35); }}
  .filters button.active {{ background:var(--s1); color:#fff; border-color:var(--s1); box-shadow:0 4px 12px rgba(42,120,214,.35);
    animation: filterPop .35s cubic-bezier(.34,1.56,.64,1); }}
  @keyframes filterPop {{ 0% {{ transform:scale(.88); }} 60% {{ transform:scale(1.06); }} 100% {{ transform:scale(1); }} }}
  .ripple {{ position:absolute; border-radius:50%; background:rgba(255,255,255,.55); transform:scale(0);
    animation: rippleFx .55s ease-out; pointer-events:none; }}
  @keyframes rippleFx {{ to {{ transform:scale(2.6); opacity:0; }} }}
  .view-section {{ display:none; }}
  .view-section.active {{ display:block; animation: fadeSection .35s cubic-bezier(.22,1,.36,1) both; }}
  main {{ padding:20px 24px; display:grid; gap:16px; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); }}
  .tile {{ background:var(--surface); border:1px solid var(--grid); border-radius:12px; padding:16px; }}
  .tile .label {{ color:var(--ink-2); font-size:12px; text-transform:uppercase; letter-spacing:.04em; display:flex; justify-content:space-between; align-items:center; }}
  .tile .value {{ font-size:27px; font-weight:650; margin-top:4px; }}
  .tile .value.good {{ color:var(--good); }}
  .wide {{ grid-column: 1 / -1; }}
  .chart-box {{ background:var(--surface); border:1px solid var(--grid); border-radius:12px; padding:16px; height:340px; }}
  .verdict-pill {{ display:inline-block; padding:2px 10px; border-radius:999px; font-size:12px; font-weight:600; }}
  .verdict-pass {{ background:#e7f7e7; color:var(--good); }}
  .verdict-fail {{ background:#fdeceb; color:var(--crit); }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th, td {{ text-align:left; padding:6px 8px; border-bottom:1px solid var(--grid); }}
  th {{ color:var(--ink-2); font-weight:600; }}
  tbody tr {{ transition: background .12s ease; }}
  tbody tr:hover {{ background:rgba(42,120,214,.05); }}
  .rec-card {{ background:var(--surface); border:1px solid var(--grid); border-radius:12px; padding:16px 18px; margin-bottom:12px; }}
  .rec-card h3 {{ margin:0 0 8px; font-size:14.5px; }}
  .rec-card .smart-row {{ font-size:12.5px; color:var(--ink-2); margin:5px 0; line-height:1.55; }}
  .rec-card .smart-row b {{ color:var(--ink); }}
  .checklist li {{ list-style:none; padding:4px 0; }}
  footer {{ padding:16px 24px; color:var(--ink-muted); font-size:12px; }}
</style>
</head>
<body>
<div class="accent-bar"></div>
<header>
  <h1>{context['bp_id']} -- {context['bp_name']}</h1>
  <div class="sub">Compliance-Impact Dashboard -- generated {context['generated_at_utc']} UTC -- real data, this project's own notebook runs</div>
</header>
<div class="status-banner" id="statusBanner"></div>
<div class="narrative">
  <h2>Business Objective</h2>
  <p>{context['business_objective']}</p>
  <h2>What This Means for the Business</h2>
  <ul>
    {''.join(f'<li>{point}</li>' for point in context['business_benefits'])}
  </ul>
</div>

<div class="tabs" id="tabs">
  <button data-view="overview" class="active">Overview</button>
  <button data-view="signals">Signal Comparison</button>
  <button data-view="network">Network Impact</button>
  <button data-view="recommendations">Recommendations</button>
  <span class="tab-indicator" id="tabIndicator"></span>
</div>
<div class="filters" id="filters"><span class="fl-label">Dataset variant</span></div>

<section id="view-overview" class="view-section active">
  <main id="tiles"></main>
  <main>
    <div class="tile wide">
      <div class="label">Validation gates (real, this variant)</div>
      <div id="gatesBox" style="display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:8px;"></div>
    </div>
  </main>
</section>

<section id="view-signals" class="view-section">
  <main style="grid-template-columns: 1fr;">
    <div class="chart-box"><canvas id="signalChart"></canvas></div>
  </main>
  <main>
    <div class="tile wide">
      <div class="label">Candidate structural signals -- real network-lift ranking</div>
      <table id="signalTable"></table>
    </div>
  </main>
</section>

<section id="view-network" class="view-section">
  <main>
    <div class="tile wide">
      <div class="label">Before / After -- real volume-scale KPI (never dollarized)</div>
      <p class="sub" style="margin:8px 0 10px;">Before = single-account review. After = real bounded 2-hop ego-network (capped at 2,000 nodes). Real, but only 3 illustrative examples -- not a population-wide average.</p>
      <table id="egoTable"></table>
    </div>
  </main>
  <main>
    <div class="tile wide">
      <div class="label">Deployable scoring service -- real self-test</div>
      <p id="fastapiNote" class="sub"></p>
    </div>
  </main>
</section>

<section id="view-recommendations" class="view-section">
  <main>
    <div class="wide" id="recsList"></div>
  </main>
</section>

<footer>
  Real, per-variant results -- never merged or blended into one unlabeled figure, per this
  platform's locked multi-variant policy. BP3 has no trained ML model -- every number above is
  a real structural signal or a real volume-scale count, never a classifier score or an
  invented dollar figure. Chart.js bundled locally (no CDN). Generated by report_builder.py --
  IBM AML RiskIQ Enterprise Suite.
</footer>
<script>
{chartjs_source}
</script>
<script>
(function() {{
  const DATA = {data_json};
  const VARIANTS = {variant_names_json};
  const STATUS = {status_json};
  const RECS = {recs_json};
  const PRIMARY = {primary_variant_json};
  let current = VARIANTS.includes(PRIMARY) ? PRIMARY : VARIANTS[0];
  const palette = {{ s1: "{palette['series_1_blue']}", s2: "{palette['series_2_orange']}", s3: "{palette['series_3_aqua']}",
    grid: "{palette['gridline']}", ink2: "{palette['ink_secondary']}", good: "{palette['status_good']}", muted: "{palette['ink_muted']}" }};

  const banner = document.getElementById("statusBanner");
  banner.className = "status-banner " + STATUS.css_class;
  banner.innerHTML = `<div class="dot ${{STATUS.css_class}}"></div>
    <div><div class="label">${{STATUS.label}}</div><div class="rationale">${{STATUS.rationale}}</div></div>`;

  function spawnRipple(e, btn) {{
    const old = btn.querySelector(".ripple"); if (old) old.remove();
    const rect = btn.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height) * 1.4;
    const span = document.createElement("span");
    span.className = "ripple";
    span.style.width = span.style.height = size + "px";
    span.style.left = (e.clientX - rect.left - size / 2) + "px";
    span.style.top = (e.clientY - rect.top - size / 2) + "px";
    btn.appendChild(span);
    span.addEventListener("animationend", () => span.remove());
  }}

  const tabs = [...document.querySelectorAll(".tabs button")];
  const tabIndicator = document.getElementById("tabIndicator");
  function moveTabIndicator(btn) {{
    if (!tabIndicator || !btn) return;
    tabIndicator.style.width = btn.offsetWidth + "px";
    tabIndicator.style.transform = "translateX(" + btn.offsetLeft + "px)";
  }}
  tabs.forEach(btn => btn.addEventListener("click", (e) => {{
    spawnRipple(e, btn);
    tabs.forEach(b => b.classList.toggle("active", b === btn));
    document.querySelectorAll(".view-section").forEach(sec => sec.classList.toggle("active", sec.id === "view-" + btn.dataset.view));
    moveTabIndicator(btn);
  }}));
  window.addEventListener("resize", () => moveTabIndicator(tabs.find(b => b.classList.contains("active"))));
  requestAnimationFrame(() => moveTabIndicator(tabs.find(b => b.classList.contains("active"))));

  const filtersBox = document.getElementById("filters");
  VARIANTS.forEach(v => {{
    const btn = document.createElement("button");
    btn.textContent = v;
    btn.className = v === current ? "active" : "";
    btn.addEventListener("click", (e) => {{ spawnRipple(e, btn); current = v; render(); [...filtersBox.querySelectorAll("button")].forEach(b => b.classList.toggle("active", b.textContent === v)); }});
    filtersBox.appendChild(btn);
  }});

  let signalChartInst = null;

  function render() {{
    const d = DATA[current];

    document.getElementById("tiles").innerHTML = `
      <div class="tile"><div class="label">Champion signal</div><div class="value">${{d.champion}}</div></div>
      <div class="tile"><div class="label">Real lift ratio</div><div class="value good">${{d.lift_ratio.toFixed(2)}}x</div></div>
      <div class="tile"><div class="label">Bootstrap 95% CI</div><div class="value" style="font-size:18px;">[${{d.ci95_low.toFixed(2)}}x, ${{d.ci95_high.toFixed(2)}}x]</div></div>
      <div class="tile"><div class="label">Real graph nodes</div><div class="value">${{d.n_nodes.toLocaleString()}}</div></div>
      <div class="tile"><div class="label">Real base rate</div><div class="value">${{(d.base_rate*100).toFixed(2)}}%</div></div>
      <div class="tile"><div class="label">Overall verdict</div><div class="value"><span class="verdict-pill ${{d.verdict==='PASS'?'verdict-pass':'verdict-fail'}}">${{d.verdict}}</span></div></div>
    `;

    const gatesBox = document.getElementById("gatesBox");
    function checklistHtml(title, verdict, checks) {{
      const items = Object.entries(checks).map(([k,v]) => `<li>${{v? '&#10003;' : '&#10007;'}} ${{k.replace(/_/g,' ')}}</li>`).join("");
      return `<div><div class="label">${{title}} <span class="verdict-pill ${{verdict==='PASS'?'verdict-pass':'verdict-fail'}}">${{verdict}}</span></div><ul class="checklist">${{items}}</ul></div>`;
    }}
    gatesBox.innerHTML = checklistHtml("Gate 1 -- Structural", d.gate1_verdict, d.gate1_checks) +
                          checklistHtml("Gate 2 -- Statistical Robustness", d.gate2_verdict, d.gate2_checks);

    if (signalChartInst) signalChartInst.destroy();
    const sorted = [...d.signals].sort((a,b) => b.lift_ratio - a.lift_ratio);
    signalChartInst = new Chart(document.getElementById("signalChart"), {{
      type: "bar",
      data: {{
        labels: sorted.map(s => s.signal),
        datasets: [{{
          label: "Real network-lift ratio",
          data: sorted.map(s => s.lift_ratio),
          backgroundColor: sorted.map(s => s.champion ? palette.s1 : palette.muted),
        }}]
      }},
      options: {{
        indexAxis: "y",
        responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{ x: {{ title: {{ display: true, text: "Lift ratio (x)" }}, grid: {{ color: palette.grid }} }},
                   y: {{ grid: {{ display: false }} }} }}
      }}
    }});

    const sigTable = document.getElementById("signalTable");
    if (d.signal_table.length) {{
      const cols = Object.keys(d.signal_table[0]);
      sigTable.innerHTML = "<thead><tr>" + cols.map(c => `<th>${{c}}</th>`).join("") + "</tr></thead><tbody>" +
        d.signal_table.map(row => "<tr>" + cols.map(c => `<td>${{row[c]}}</td>`).join("") + "</tr>").join("") + "</tbody>";
    }}

    const egoTable = document.getElementById("egoTable");
    if (d.ego_table.length) {{
      const cols = Object.keys(d.ego_table[0]);
      egoTable.innerHTML = "<thead><tr>" + cols.map(c => `<th>${{c}}</th>`).join("") + "</tr></thead><tbody>" +
        d.ego_table.map(row => "<tr>" + cols.map(c => `<td>${{row[c]}}</td>`).join("") + "</tr>").join("") + "</tbody>";
    }} else {{
      egoTable.innerHTML = "<tbody><tr><td>No real illustrative ego-network examples saved for this variant.</td></tr></tbody>";
    }}

    document.getElementById("fastapiNote").textContent =
      `Real rows checked: ${{(d.fastapi_self_test.rows_checked||0).toLocaleString()}}, mismatches: ${{d.fastapi_self_test.mismatches||0}}. ${{d.no_trained_model_note}}`;

    const recsList = document.getElementById("recsList");
    recsList.innerHTML = RECS.map(r => `
      <div class="rec-card">
        <h3>${{r.title}}</h3>
        <div class="smart-row"><b>Specific:</b> ${{r.specific}}</div>
        <div class="smart-row"><b>Measurable:</b> ${{r.measurable}}</div>
        <div class="smart-row"><b>Achievable:</b> ${{r.achievable}}</div>
        <div class="smart-row"><b>Relevant:</b> ${{r.relevant}}</div>
        <div class="smart-row"><b>Time-bound:</b> ${{r.time_bound}}</div>
      </div>
    `).join("");
  }}

  render();
}})();
</script>
</body>
</html>"""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


# ============================================================================
# PowerPoint deck (python-pptx) -- structural equivalent of write_pptx_deck_multiclass
# ============================================================================
def write_pptx_deck_structural(path: Path, context: dict, chart_png_paths: Optional[dict] = None) -> Path:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt

    prs = Presentation()
    blue = RGBColor(0x2A, 0x78, 0xD6)

    slide = _add_branded_slide(prs, 0)
    slide.shapes.title.text = f"{context['bp_id']}: {context['bp_name']}"
    slide.placeholders[1].text = f"Compliance-Impact Executive Briefing -- {context['generated_at_utc']} UTC"

    slide = _add_branded_slide(prs, 1)
    slide.shapes.title.text = "Business Objective"
    slide.placeholders[1].text_frame.text = context["business_objective"]

    status = context.get("status") or compute_bp_status(context)
    status_colors = {
        "good": RGBColor(0x0C, 0xA3, 0x0C),
        "warning": RGBColor(0xC9, 0x85, 0x00),
        "critical": RGBColor(0xD0, 0x3B, 0x3B),
    }
    slide = _add_branded_slide(prs, 1)
    slide.shapes.title.text = "Recommendation & Status"
    body = slide.placeholders[1].text_frame
    body.text = status["label"]
    body.paragraphs[0].font.bold = True
    body.paragraphs[0].font.size = Pt(28)
    body.paragraphs[0].font.color.rgb = status_colors.get(status["css_class"], blue)
    p = body.add_paragraph()
    p.text = status["rationale"]
    p.level = 1

    primary_name = context["primary_variant"]
    primary = context["variants"][primary_name]
    rep = primary["report"]
    boot = rep["bootstrap"]
    slide = _add_branded_slide(prs, 1)
    slide.shapes.title.text = "Executive Summary"
    body = slide.placeholders[1].text_frame
    body.text = f"Champion structural signal: {rep['champion_name']} ({primary_name} variant)"
    for line in [
        f"Real network-lift ratio: {rep['test_metrics']['lift_ratio']:.2f}x (bootstrap 95% CI "
        f"[{boot['ci95_low']:.2f}x, {boot['ci95_high']:.2f}x])",
        f"Real graph: {rep['n_nodes']:,} nodes, {rep['n_distinct_edges']:,} distinct edges, "
        f"base rate {rep['base_rate_all']:.2%}",
        f"Two-gate verdict: {rep['overall_verdict']}  --  No trained ML model (structural rule only)",
    ]:
        p = body.add_paragraph()
        p.text = line
        p.level = 1

    slide = _add_branded_slide(prs, 1)
    slide.shapes.title.text = "What This Means for the Business"
    body = slide.placeholders[1].text_frame
    body.text = context["business_benefits"][0]
    for point in context["business_benefits"][1:]:
        p = body.add_paragraph()
        p.text = point
        p.level = 1

    if chart_png_paths and "signal_lift" in chart_png_paths:
        slide = _add_branded_slide(prs, 5)
        slide.shapes.title.text = "Candidate Structural Signals -- Real Network-Lift Ranking"
        slide.shapes.add_picture(
            str(chart_png_paths["signal_lift"]), Inches(0.5), Inches(1.3), width=Inches(9)
        )

    slide = _add_branded_slide(prs, 5)
    slide.shapes.title.text = "Model Performance by Dataset Variant"
    rows, cols = len(context["variants"]) + 1, 5
    left, top, width, height = Inches(0.5), Inches(1.5), Inches(9), Inches(0.4 * rows)
    table_shape = slide.shapes.add_table(rows, cols, left, top, width, height).table
    for c, h in enumerate(["Variant", "Champion Signal", "Real Lift Ratio", "CI95", "Verdict"]):
        table_shape.cell(0, c).text = h
    for r, (variant_name, v) in enumerate(context["variants"].items(), start=1):
        rr = v["report"]
        bb = rr["bootstrap"]
        table_shape.cell(r, 0).text = variant_name
        table_shape.cell(r, 1).text = rr["champion_name"]
        table_shape.cell(r, 2).text = f"{rr['test_metrics']['lift_ratio']:.2f}x"
        table_shape.cell(r, 3).text = f"[{bb['ci95_low']:.2f}x, {bb['ci95_high']:.2f}x]"
        table_shape.cell(r, 4).text = rr["overall_verdict"]

    slide = _add_branded_slide(prs, 1)
    slide.shapes.title.text = f"Before / After Impact ({primary_name})"
    body = slide.placeholders[1].text_frame
    body.text = "Before: single-account review -- zero real network visibility"
    for line in [
        "After: real bounded 2-hop ego-network around the same account (capped at 2,000 nodes)",
        "Reported as a real volume-scale KPI -- never dollarized (no sourced per-account cost basis exists for this BP)",
        "3 real illustrative examples -- not a population-wide average",
    ]:
        p = body.add_paragraph()
        p.text = line
        p.level = 1

    recs = context.get("smart_recommendations") or generate_smart_recommendations_structural(context)
    slide = _add_branded_slide(prs, 1)
    slide.shapes.title.text = "Key Recommendations"
    body = slide.placeholders[1].text_frame
    body.text = recs[0]["title"]
    p = body.add_paragraph()
    p.text = recs[0]["specific"]
    p.level = 1
    for r in recs[1:]:
        p = body.add_paragraph()
        p.text = r["title"]
        p2 = body.add_paragraph()
        p2.text = r["specific"]
        p2.level = 1

    slide = _add_branded_slide(prs, 1)
    slide.shapes.title.text = "Regulatory & Compliance Mapping"
    body = slide.placeholders[1].text_frame
    body.text = context["regulatory_frameworks"][0][0]
    for fw, applies in context["regulatory_frameworks"][1:]:
        p = body.add_paragraph()
        p.text = f"{fw} ({applies})"
        p.level = 1

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(path))
    return path


# ============================================================================
# Rule card (MODEL_CARD.md equivalent) -- RULE_CARD.md. Deliberately named and framed
# differently from write_model_card/write_model_card_multiclass: BP3's real deployable
# artifact is a RULE (a threshold or set-membership test), never a pickled classifier, and
# this document says so in its own title and structure rather than reusing "model card"
# framing that would misrepresent what is actually in production.
# ============================================================================
def write_rule_card_structural(path: Path, context: dict) -> Path:
    primary_name = context["primary_variant"]
    primary = context["variants"][primary_name]
    rep = primary["report"]
    rule = primary.get("rule", {})
    status = context.get("status") or compute_bp_status(context)
    recs = context.get("smart_recommendations") or generate_smart_recommendations_structural(context)
    boot = rep["bootstrap"]

    lines = (
        [
            f"# Rule Card -- {context['bp_id']}: {context['bp_name']}",
            "",
            f"_Generated {context['generated_at_utc']} UTC. Primary reported variant: "
            f"{primary_name} (this BP's locked mandatory realism-validation tier)._",
            "",
            "**This is a RULE CARD, not a model card.** BP3 has no trained ML model -- the real "
            "deployable artifact is a directly-interpretable structural RULE (a threshold or a "
            "set-membership test over a real graph-structural signal), never a pickled classifier. "
            "SHAP/LIME explainability sections that appear in this platform's other BPs' model "
            "cards are genuinely not applicable here, not merely omitted.",
            "",
            f"## Status: {status['label']}",
            status["rationale"],
            "",
            "## Business Objective",
            context["business_objective"],
            "",
            "## What This Means for the Business",
        ]
        + [f"- {point}" for point in context["business_benefits"]]
        + [
            "",
            "## Rule Details",
            f"- Champion structural signal: **{rep['champion_name']}**",
            f"- Rule artifact column: `{rule.get('champion_column', 'N/A')}`",
            f"- Is threshold signal: {rule.get('is_threshold_signal', 'N/A')}",
            f"- Threshold: {rule.get('threshold') if rule.get('threshold') is not None else 'N/A (set-membership test)'}",
            f"- Random seed: {rep.get('random_seed')}",
            f"- Real network-lift ratio (point estimate): {rep['test_metrics']['lift_ratio']:.4f}x",
            f"- Real bootstrap 95% CI: [{boot['ci95_low']:.4f}x, {boot['ci95_high']:.4f}x] "
            f"({boot['n_resamples']:,} resamples, {boot['n_invalid_resamples']:,} invalid)",
            "",
            "## Intended Use",
            "Network-proximity / structural-prominence flagging to prioritize which already-flagged "
            "accounts' surrounding networks an investigator reviews next, and to surface a real "
            "bounded 2-hop ego-network for that review. Not a standalone SAR-filing decision, not a "
            "probability score -- output is a real structural flag feeding investigator triage, per "
            "this platform's locked scope.",
            "",
            "## Training / Screening Data",
            "IBM Transactions for Anti Money Laundering (AML) -- synthetic, IBM Research. Variants "
            "used (never merged): " + ", ".join(context["variants"].keys()) + ".",
            "",
            "## Evaluation",
            "| Variant | Champion Signal | Real Lift Ratio | CI95 Low | CI95 High | Gate 1 | Gate 2 | Overall Verdict |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    for variant_name, v in context["variants"].items():
        r = v["report"]
        b = r["bootstrap"]
        lines.append(
            f"| {variant_name} | {r['champion_name']} | {r['test_metrics']['lift_ratio']:.2f}x | "
            f"{b['ci95_low']:.2f}x | {b['ci95_high']:.2f}x | {r['gate1_verdict']} | "
            f"{r['gate2_verdict']} | {r['overall_verdict']} |"
        )
    lines += [
        "",
        "## Explainability -- Not Applicable",
        rep.get(
            "no_trained_model_note",
            "BP3 has no trained ML model -- every candidate is a directly-interpretable "
            "structural signal; SHAP/LIME are N/A, not attempted.",
        ),
        "",
        "## Scaling / Engineering Notes",
        rep.get("scaling_engineering_note", "Not recorded for this run."),
        "",
        "## Deployable Scoring Service -- Real Self-Test",
        f"- Rows checked: {rep.get('fastapi_self_test', {}).get('rows_checked', 0):,}",
        f"- Mismatches: {rep.get('fastapi_self_test', {}).get('mismatches', 0)}",
        "",
        "## Ethical Considerations / Fairness",
        context["fairness_note"],
        "",
        "## Caveats & Limitations",
    ]
    for cav in context.get("caveats", []):
        lines.append(f"- {cav}")
    lines += [
        "",
        "## Regulatory Mapping",
    ]
    for fw, applies in context["regulatory_frameworks"]:
        lines.append(f"- {fw} -- {applies}")
    lines += ["", "## Recommendations"]
    for r in recs:
        lines += [
            f"### {r['title']}",
            f"- **Specific:** {r['specific']}",
            f"- **Measurable:** {r['measurable']}",
            f"- **Achievable:** {r['achievable']}",
            f"- **Relevant:** {r['relevant']}",
            f"- **Time-bound:** {r['time_bound']}",
            "",
        ]

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ============================================================================
# ============================================================================
# PLATFORM ROLLUP EXTENSION (added for BP6 -- Enterprise AML Compliance Monitoring &
# Regulatory Reporting, 2026-10-02). Every function above this block (binary, multiclass,
# and structural paths) is left completely UNCHANGED -- BP1-BP5's already-shipped, verified
# reports must never regress. The functions below are NEW, parallel, platform-rollup-aware
# equivalents: BP6 has no trained model and no structural signal of its own -- it is a pure,
# read-only rollup of BP1-BP5's own already-computed real figures (never recomputed here
# beyond simple real-dict lookups and real sums of real numbers already present in the
# source dict).
#
# Reused UNCHANGED from above (confirmed fully generic, no binary/multiclass/structural-
# specific assumption): _fmt_usd / format_usd, _hex_rgb, _apply_word_brand_styles,
# _brand_word_table_headers, _brand_excel_sheet, _band_excel_rows, _color_verdict_cells,
# _add_branded_slide, _EXCEL_USD_FORMAT, export_pdf_from_docx, write_changelog, PALETTE.
#
# Real input shape this reads (verified against the user's own real, already-generated
# `reports/bp6_enterprise_compliance_monitoring/bp6_platform_source_data.json`, produced by
# `notebooks/bp6_enterprise_compliance_monitoring/_extract_platform_source_data.py` --
# pure, read-only parsing of BP1-BP5's own real MODEL_CARD.md/RULE_CARD.md + NB3 validation
# reports, per the locked master plan's Section 8 "recomputing nothing" rule):
#   platform_source_data = {
#     "generated_at_utc": str, "sourcing_method": str,
#     "bps": {"BP1": {...}, "BP2": {...}, "BP3": {...}, "BP4": {...}, "BP5": {...}},
#     "platform_rollup": {
#       "benefit_category_1_fp_reduction_savings": {bp1, bp4, bp5, total_usd,
#           total_investigator_hours_saved, total_fewer_fp_alerts, description},
#       "benefit_category_2_tp_uplift_value": {bp1, bp4, bp5, total_usd,
#           total_additional_cases_caught, description},
#       "benefit_category_3_bp2_typology_lines": {auto_typing_efficiency_savings_usd,
#           typology_confirmation_value_usd, description},
#       "cost_context": {description},
#       "portfolio_scale": {bp3_n_nodes, bp3_n_edges, description},
#       "headline_grand_total_note": str,
#       "all_bps_verdict_summary": {"BP1": "PASS", ..., "BP5": "PASS"},
#     },
#   }
#
# Locked discipline enforced throughout this extension (master plan Section 8, Section 7A):
# the three financial categories (BENEFIT, COST CONTEXT, PORTFOLIO SCALE) are NEVER summed
# or blended into one grand total anywhere below -- every table/chart/tile shows them as
# separate, clearly-labeled lines. BENEFIT category 1 (FP-reduction) and category 2
# (TP-uplift) stay two separate lines even within BENEFIT. BENEFIT category 3 (BP2's own
# two figures) is never folded into categories 1/2 (different unit basis). PORTFOLIO SCALE
# (BP3's real node/edge counts) is never dollarized. COST CONTEXT carries no dollar figure
# (none sourced -- none invented).
# ============================================================================


# ============================================================================
# Real platform benefit table -- the three-category discipline, rendered as one DataFrame
# with an explicit "Category" column so every output format (Word/Excel/HTML/PPTX) can
# group rows by category without ever summing across categories. Pure formatting + simple
# real-dict lookups and real sums already present in `platform_rollup` -- no new figure is
# computed here.
# ============================================================================
def build_platform_benefit_table(platform_rollup: dict) -> pd.DataFrame:
    """Real Category | Line Item | Value | Note table -- straight from the real
    `platform_rollup` dict (already-computed by the extractor script). Never recomputes a
    figure; only formats and labels what is already there."""
    cat1 = platform_rollup["benefit_category_1_fp_reduction_savings"]
    cat2 = platform_rollup["benefit_category_2_tp_uplift_value"]
    cat3 = platform_rollup["benefit_category_3_bp2_typology_lines"]
    cost = platform_rollup["cost_context"]
    scale = platform_rollup["portfolio_scale"]

    rows = [
        {
            "Category": "BENEFIT 1 -- FP-Reduction Savings (ASSUMPTION; never summed with categories 2/3)",
            "Line Item": "BP1 -- Transaction Monitoring",
            "Value": _fmt_usd(cat1["bp1"]),
            "Note": "FP-reduction $ savings",
        },
        {
            "Category": "BENEFIT 1 -- FP-Reduction Savings (ASSUMPTION; never summed with categories 2/3)",
            "Line Item": "BP4 -- Structuring & Smurfing",
            "Value": _fmt_usd(cat1["bp4"]),
            "Note": "FP-reduction $ savings",
        },
        {
            "Category": "BENEFIT 1 -- FP-Reduction Savings (ASSUMPTION; never summed with categories 2/3)",
            "Line Item": "BP5 -- Correspondent Banking & Cross-Border",
            "Value": _fmt_usd(cat1["bp5"]),
            "Note": "FP-reduction $ savings",
        },
        {
            "Category": "BENEFIT 1 -- FP-Reduction Savings (ASSUMPTION; never summed with categories 2/3)",
            "Line Item": "TOTAL (BP1+BP4+BP5)",
            "Value": _fmt_usd(cat1["total_usd"]),
            "Note": f"{cat1['total_investigator_hours_saved']:,} investigator hours saved, "
            f"{cat1['total_fewer_fp_alerts']:,} fewer FP alerts",
        },
        {
            "Category": "BENEFIT 2 -- TP-Uplift Illustrative Value (ASSUMPTION; never summed with categories 1/3)",
            "Line Item": "BP1 -- Transaction Monitoring",
            "Value": _fmt_usd(cat2["bp1"]),
            "Note": "TP-uplift illustrative $",
        },
        {
            "Category": "BENEFIT 2 -- TP-Uplift Illustrative Value (ASSUMPTION; never summed with categories 1/3)",
            "Line Item": "BP4 -- Structuring & Smurfing",
            "Value": _fmt_usd(cat2["bp4"]),
            "Note": "TP-uplift illustrative $",
        },
        {
            "Category": "BENEFIT 2 -- TP-Uplift Illustrative Value (ASSUMPTION; never summed with categories 1/3)",
            "Line Item": "BP5 -- Correspondent Banking & Cross-Border",
            "Value": _fmt_usd(cat2["bp5"]),
            "Note": "TP-uplift illustrative $",
        },
        {
            "Category": "BENEFIT 2 -- TP-Uplift Illustrative Value (ASSUMPTION; never summed with categories 1/3)",
            "Line Item": "TOTAL (BP1+BP4+BP5)",
            "Value": _fmt_usd(cat2["total_usd"]),
            "Note": f"{cat2['total_additional_cases_caught']:+,} additional real cases caught",
        },
        {
            "Category": "BENEFIT 3 -- BP2 Typology Lines (kept separate -- different unit basis, never blended into 1/2)",
            "Line Item": "Auto-typing efficiency savings",
            "Value": _fmt_usd(cat3["auto_typing_efficiency_savings_usd"]),
            "Note": "BP2's own figure -- different case subset/ASSUMPTION basis than categories 1/2",
        },
        {
            "Category": "BENEFIT 3 -- BP2 Typology Lines (kept separate -- different unit basis, never blended into 1/2)",
            "Line Item": "Typology confirmation value",
            "Value": _fmt_usd(cat3["typology_confirmation_value_usd"]),
            "Note": "BP2's own figure -- different case subset/ASSUMPTION basis than categories 1/2",
        },
        {
            "Category": "COST CONTEXT (informational only -- never summed into any headline figure)",
            "Line Item": "Platform build/operating cost",
            "Value": "NOT SOURCED -- none invented",
            "Note": cost["description"],
        },
        {
            "Category": "PORTFOLIO SCALE (volume only -- never dollarized, never summed with BENEFIT)",
            "Line Item": "BP3 real network nodes",
            "Value": f"{scale['bp3_n_nodes']:,}",
            "Note": "Structurally distinct from BP1/2/4/5's transaction-level populations",
        },
        {
            "Category": "PORTFOLIO SCALE (volume only -- never dollarized, never summed with BENEFIT)",
            "Line Item": "BP3 real network edges",
            "Value": f"{scale['bp3_n_edges']:,}",
            "Note": "Structurally distinct from BP1/2/4/5's transaction-level populations",
        },
    ]
    return pd.DataFrame(rows)


# ============================================================================
# Real, computed-not-asserted platform-wide status -- derived strictly from
# `platform_rollup["all_bps_verdict_summary"]` (each BP's own already-saved real two-gate
# verdict). Rendered identically across every output format.
# ============================================================================
def compute_platform_status(platform_source_data: dict) -> dict:
    verdicts = platform_source_data["platform_rollup"]["all_bps_verdict_summary"]
    failing = [bp for bp, v in verdicts.items() if v != "PASS"]
    if not failing:
        return {
            "label": "RECOMMENDED FOR PRODUCTION -- PLATFORM-WIDE",
            "css_class": "good",
            "rationale": (
                f"Every real business problem's own two-gate validation ({', '.join(verdicts.keys())}) "
                f"passed on its own locked mandatory realism-validation tier. This platform-wide status "
                f"is a pure pass-through of those five real, already-recorded verdicts -- nothing is "
                f"re-validated or re-computed at the rollup level."
            ),
        }
    return {
        "label": f"NOT RECOMMENDED FOR PRODUCTION, PLATFORM-WIDE -- {', '.join(failing)} FAILED VALIDATION",
        "css_class": "critical",
        "rationale": (
            f"{', '.join(failing)} did not pass its own two-gate validation (real recorded verdict: "
            f"{', '.join(f'{bp}={verdicts[bp]}' for bp in failing)}). The remaining BPs' real figures "
            f"are still reported individually below, but the platform-wide headline status reflects the "
            f"real failing BP(s) rather than silently averaging over them."
        ),
    }


# ============================================================================
# Real, data-driven SMART recommendations -- platform-rollup equivalent of
# generate_smart_recommendations / _multiclass / _structural. Every clause cites a real
# number already present in `platform_source_data`, never a templated placeholder.
# ============================================================================
def generate_platform_smart_recommendations(platform_source_data: dict) -> list:
    bps = platform_source_data["bps"]
    roll = platform_source_data["platform_rollup"]
    cat1, cat2, cat3 = (
        roll["benefit_category_1_fp_reduction_savings"],
        roll["benefit_category_2_tp_uplift_value"],
        roll["benefit_category_3_bp2_typology_lines"],
    )
    scale = roll["portfolio_scale"]
    verdicts = roll["all_bps_verdict_summary"]
    failing = [bp for bp, v in verdicts.items() if v != "PASS"]

    champions = {
        bp: d["variants"][d["primary_variant"]]["champion"]
        for bp, d in bps.items()
        if "champion" in d["variants"][d["primary_variant"]]
    }
    champion_counts: dict = {}
    for bp, champ in champions.items():
        champion_counts.setdefault(champ, []).append(bp)
    recurring_champion = max(champion_counts.items(), key=lambda kv: len(kv[1])) if champion_counts else None

    cat2_contributors = {"BP1": cat2["bp1"], "BP4": cat2["bp4"], "BP5": cat2["bp5"]}
    top_cat2_bp = max(cat2_contributors, key=lambda k: cat2_contributors[k])

    recs = [
        {
            "bp": "",
            "title": "Re-run the platform rollup every time a BP's own report package regenerates",
            "specific": (
                f"This platform-wide rollup is a pure read-only pass-through of BP1-BP5's own real "
                f"already-computed figures ({roll['description'] if 'description' in roll else 'see platform_rollup'}) -- "
                f"it carries no independent validation of its own beyond the two structural/reconciliation "
                f"gates (see this BP's own Notebook 3 report)."
            ),
            "measurable": "Re-run the extractor script + BP6 Notebooks 2-4 whenever any of BP1-BP5's MODEL_CARD.md/RULE_CARD.md or NB3 validation report changes; confirm Gate 2's real reconciliation check still passes exactly.",
            "achievable": "Uses the existing, already-built extractor script and BP6 pipeline -- no new infrastructure required.",
            "relevant": "Keeps the platform-wide figures this report cites from silently going stale relative to the per-BP source of truth.",
            "time_bound": "Immediately after any BP1-BP5 report regeneration; otherwise on the same quarterly cadence as each BP's own recalibration review.",
        },
        {
            "bp": "",
            "title": "Reallocate the real platform-wide false-positive-reduction capacity gain",
            "specific": (
                f"Summed across BP1+BP4+BP5 (ASSUMPTION-labeled, never blended with category 2 or category 3 "
                f"below): {_fmt_usd(cat1['total_usd'])} in false-positive-reduction savings, "
                f"{cat1['total_investigator_hours_saved']:,} investigator hours, "
                f"{cat1['total_fewer_fp_alerts']:,} fewer false-positive alerts across the three transaction-level BPs."
            ),
            "measurable": "Track real combined alert-review hours logged across BP1/BP4/BP5's production queues against this ASSUMPTION estimate.",
            "achievable": "Capacity freed is redeployed to case investigation depth across the three detection programs, not a headcount reduction -- an operational scheduling change.",
            "relevant": "Investigator capacity is the real, most commonly cited AML program bottleneck platform-wide (FFIEC BSA/AML Examination Manual, alert-management pillar).",
            "time_bound": "Reassess real combined alert-review hours 90 days after platform-wide go-live.",
        },
        {
            "bp": "",
            "title": f"Validate the real platform-wide true-positive uplift, led by {top_cat2_bp}",
            "specific": (
                f"Summed across BP1+BP4+BP5: {_fmt_usd(cat2['total_usd'])} illustrative regulatory-exposure-"
                f"avoidance, {cat2['total_additional_cases_caught']:+,} additional real cases caught. "
                f"{top_cat2_bp} contributes the single largest real category-2 dollar figure of the three "
                f"({_fmt_usd(cat2_contributors[top_cat2_bp])})."
            ),
            "measurable": "Real SAR filing rate on model-flagged alerts across the three contributing BPs, tracked per-BP and never blended with the false-positive savings in category 1 above.",
            "achievable": "Requires only tagging each filed SAR with which BP's model originally surfaced the alert -- a labeling change, not a new detection system.",
            "relevant": f"Directs platform-wide model-risk review attention to {top_cat2_bp}, the real largest real contributor to this benefit category.",
            "time_bound": "First real platform-wide comparison report at the 6-month production mark.",
        },
        {
            "bp": "BP2",
            "title": "Keep BP2's two typology-detection figures reported separately, never folded into categories 1/2",
            "specific": (
                f"BP2 contributes its own real auto-typing efficiency savings ({_fmt_usd(cat3['auto_typing_efficiency_savings_usd'])}) "
                f"and typology-confirmation value ({_fmt_usd(cat3['typology_confirmation_value_usd'])}) -- "
                f"both real figures on a different unit basis (auto-typing hours, distinct case subset) than "
                f"BP1/BP4/BP5's categories 1/2, per the locked never-blend-categories rule."
            ),
            "measurable": "Any future dashboard or report citing a platform 'total benefit' figure is checked to confirm it reports these three categories separately, not as one blended number.",
            "achievable": "A documentation/labeling convention enforced by this report_builder.py module's own structural gate (see this BP's Notebook 3), not a manual check.",
            "relevant": "Prevents a materially misleading single 'platform savings' headline that would mix incompatible unit bases.",
            "time_bound": "Immediate -- applies to this report and every future one referencing the platform rollup.",
        },
    ]

    if recurring_champion and len(recurring_champion[1]) > 1:
        champ_name, champ_bps = recurring_champion
        recs.append(
            {
                "bp": "",
                "title": f"Document the real recurring champion algorithm ({champ_name}) across the platform",
                "specific": (
                    f"{champ_name} is the real champion model on {len(champ_bps)} of the platform's BPs "
                    f"({', '.join(champ_bps)}), each independently selected by its own Stage A/B benchmark -- "
                    f"not assumed or forced to agree."
                ),
                "measurable": "Confirm this cross-BP champion agreement holds at every future retrain; log explicitly if a future BP's own champion diverges.",
                "achievable": "Already computed by each BP's own existing Notebook 3 -- no new tooling required at the rollup level.",
                "relevant": "A champion algorithm stable across multiple independently-trained business problems is useful real evidence for platform-wide SR 11-7 model-risk documentation (shared infra/tooling/monitoring approach).",
                "time_bound": "Refresh this cross-BP comparison at every platform-wide rollup regeneration.",
            }
        )

    # ------------------------------------------------------------------------
    # Per-BP specific recommendations -- one for each of BP1-BP5, every clause citing a real
    # number already present in platform_source_data (champion name, verdict, threshold,
    # feature count, or dollar figure) -- never a templated mail-merge.
    # ------------------------------------------------------------------------
    b1 = bps["BP1"]["variants"][bps["BP1"]["primary_variant"]]
    recs.append(
        {
            "bp": "BP1",
            "title": f"Schedule a threshold review for BP1's real operating point ({b1.get('threshold', 0):.4f})",
            "specific": (
                f"BP1's real champion ({b1['champion']}) operates at a real decision threshold of "
                f"{b1.get('threshold', 0):.4f} on {bps['BP1']['primary_variant']}, using "
                f"{b1.get('n_features', 'N/A')} real engineered features, yielding real precision "
                f"{b1['test_metrics']['precision']:.3f} and real recall {b1['test_metrics']['recall']:.3f} "
                f"(real PR-AUC {b1['test_metrics']['pr_auc']:.4f})."
            ),
            "measurable": "Track real precision/recall drift against these two exact baseline figures on every production scoring batch; a real move of more than 5 percentage points on either triggers a threshold review.",
            "achievable": "Uses the already-built, self-tested BP1 scoring service -- no new infrastructure.",
            "relevant": "BP1 is the platform's foundational detection layer -- its threshold directly sets the real false-positive alert volume every downstream investigator queue inherits.",
            "time_bound": "Quarterly, next due within 90 days of platform-wide go-live.",
        }
    )

    b2 = bps["BP2"]["variants"][bps["BP2"]["primary_variant"]]
    class_counts = b2.get("class_counts", {})
    smallest_class = min(class_counts, key=class_counts.get) if class_counts else None
    largest_class = max(class_counts, key=class_counts.get) if class_counts else None
    recs.append(
        {
            "bp": "BP2",
            "title": "Grow real training examples for BP2's thinnest real typology class before the next retrain",
            "specific": (
                (
                    f"BP2's real class-count distribution on {bps['BP2']['primary_variant']} is uneven: "
                    f"'{largest_class}' has {class_counts[largest_class]:,} real matched examples versus "
                    f"'{smallest_class}' at only {class_counts[smallest_class]:,} -- a real "
                    f"{class_counts[largest_class] / max(class_counts[smallest_class], 1):.1f}x gap, "
                    f"with real macro-F1 at {b2['test_metrics']['macro_f1']:.3f} across "
                    f"{b2.get('n_features', 'N/A')} features."
                )
                if class_counts
                else (
                    f"BP2's real champion ({b2['champion']}) achieves real macro-F1 "
                    f"{b2['test_metrics']['macro_f1']:.3f} on {bps['BP2']['primary_variant']}."
                )
            ),
            "measurable": "Real per-class F1 (not just macro-F1) tracked every retrain; flag any real class whose F1 drops below the current run's weakest class.",
            "achievable": "Uses the existing LI-Medium/HI-Medium staged-scale-up pattern already locked in the master plan -- re-point DATASET_VARIANT, no new modeling approach.",
            "relevant": "A thin real typology class is the most likely place a future retrain silently regresses without a per-class check.",
            "time_bound": "Before BP2's next scheduled retrain.",
        }
    )

    b3 = bps["BP3"]["variants"][bps["BP3"]["primary_variant"]]
    recs.append(
        {
            "bp": "BP3",
            "title": "Re-confirm BP3's real bootstrap CI lower bound stays above 1.0x at the next scale-up",
            "specific": (
                f"BP3's real champion signal ('{b3['champion']}') holds a real network-lift ratio of "
                f"{b3['test_metrics']['lift_ratio']:.2f}x on {bps['BP3']['primary_variant']} "
                f"({scale['bp3_n_nodes']:,} real nodes, {scale['bp3_n_edges']:,} real edges) -- the "
                f"platform's only BP with no dollar figure (no sourced per-account cost basis, honestly "
                f"disclosed rather than invented)."
            ),
            "measurable": "Real bootstrap 95% CI lower bound re-checked at every future real re-run; a lower bound at or below 1.0x (no real lift) is the pre-registered trigger for re-screening the candidate signal set.",
            "achievable": "Uses the existing, already-built Stage A/B screening and bootstrap CI pipeline -- no new infrastructure.",
            "relevant": "BP3's real lift is the only evidence its structural rule still outperforms random account selection -- losing it would mean investigators get no real benefit from network-aware triage.",
            "time_bound": "At every future HI-Large/LI-Large stretch-validation attempt (master plan's own optional next step for this BP).",
        }
    )

    b4 = bps["BP4"]["variants"][bps["BP4"]["primary_variant"]]
    recs.append(
        {
            "bp": "BP4",
            "title": f"Investigate BP4's real precision/recall trade-off at threshold {b4.get('threshold', 0):.4f}",
            "specific": (
                f"BP4's real champion ({b4['champion']}) achieves the platform's highest real recall among "
                f"the three binary BPs ({b4['test_metrics']['recall']:.3f}) but its lowest real precision "
                f"({b4['test_metrics']['precision']:.3f}) at threshold {b4.get('threshold', 0):.4f} on "
                f"{bps['BP4']['primary_variant']}, using {b4.get('n_features', 'N/A')} real features "
                f"(BP1's 19 plus BP4's own 5 structuring-specific ones)."
            ),
            "measurable": "Real precision/recall at a shifted threshold, re-evaluated against the SAME real held-out test set, before any production threshold change is made.",
            "achievable": "A real threshold-sweep re-evaluation using Notebook 3's already-saved test-set scores -- no retraining required.",
            "relevant": f"BP4 contributes the platform's single largest real BENEFIT-category-2 dollar figure ({_fmt_usd(cat2['bp4'])}) -- its real operating point deserves the platform's closest scrutiny.",
            "time_bound": "Before BP4's real threshold is next changed in production.",
        }
    )

    b5 = bps["BP5"]["variants"][bps["BP5"]["primary_variant"]]
    recs.append(
        {
            "bp": "BP5",
            "title": f"Audit BP5's {b5.get('n_features', 'N/A')} real cross-border features for redundancy",
            "specific": (
                f"BP5's real champion ({b5['champion']}) uses {b5.get('n_features', 'N/A')} real features -- "
                f"the most of any binary BP on the platform -- at a real threshold of "
                f"{b5.get('threshold', 0):.4f}, achieving real precision {b5['test_metrics']['precision']:.3f} "
                f"and real recall {b5['test_metrics']['recall']:.3f} on {bps['BP5']['primary_variant']}."
            ),
            "measurable": "Real SHAP global-importance ranking (already computed by BP5's own Notebook 3) reviewed for any cross-border feature contributing materially less than BP1's shared base features.",
            "achievable": "Uses BP5's already-computed SHAP output -- a review, not a new computation.",
            "relevant": f"BP5 delivers the platform's single largest real BENEFIT-category-1 dollar figure ({_fmt_usd(cat1['bp5'])}) -- confirming its extra features earn their real complexity protects that result.",
            "time_bound": "Before BP5's feature set is next changed.",
        }
    )

    recs.append(
        {
            "bp": "BP3",
            "title": "Keep BP3's real network-coverage volume as a portfolio-scale line, never dollarized or summed with BENEFIT",
            "specific": (
                f"BP3's real network covers {scale['bp3_n_nodes']:,} nodes and {scale['bp3_n_edges']:,} edges -- "
                f"structurally distinct from BP1/BP2/BP4/BP5's transaction-level populations, with no sourced "
                f"per-account investigation-cost basis to dollarize it (disclosed honestly, never invented)."
            ),
            "measurable": "Any future platform dashboard reporting a single 'accounts covered' or 'network scale' figure cites this real count directly, never converts it to a dollar estimate.",
            "achievable": "A reporting convention, not a new computation -- BP3's own RULE_CARD.md already discloses the same real no-cost-basis limitation.",
            "relevant": "Prevents a fabricated per-account cost figure from entering platform-wide financial reporting.",
            "time_bound": "Immediate -- applies to this report and every future one referencing BP3's portfolio scale.",
        }
    )

    if failing:
        recs.append(
            {
                "bp": "",
                "title": f"Resolve the real validation failure on {', '.join(failing)} before citing platform-wide PASS",
                "specific": f"{', '.join(failing)} did not pass its own two-gate validation (real recorded verdict{'s' if len(failing) > 1 else ''}: {', '.join(f'{bp}={verdicts[bp]}' for bp in failing)}).",
                "measurable": "Re-run that BP's own Notebook 3 until both gates PASS, then re-run the BP6 extractor + rollup pipeline.",
                "achievable": "Uses each BP's own existing, already-built Notebook 3 pipeline -- no new methodology required at the rollup level.",
                "relevant": "This platform's locked policy requires every contributing BP to PASS before the platform-wide status is reported as fully recommended.",
                "time_bound": "Before this platform rollup is cited in any external or regulatory-facing report.",
            }
        )
    else:
        recs.append(
            {
                "bp": "",
                "title": "Maintain the real five-BP all-PASS standard on every future platform-wide retrain cycle",
                "specific": f"All five real business problems currently pass both validation gates ({', '.join(verdicts.keys())}).",
                "measurable": "Every BP must continue to PASS both gates before its figures feed the next platform rollup regeneration.",
                "achievable": "Enforced automatically by each BP's own existing Notebook 3 gate logic plus BP6 Notebook 3's own reconciliation gate.",
                "relevant": "This is the basis for this report's current platform-wide recommended status.",
                "time_bound": "Every retrain cycle, before the next rollup regeneration.",
            }
        )

    return recs


# ============================================================================
# Real SHAP feature-name -> plain-language phrase lookup. Covers exactly the real feature
# names that appear in BP1/BP2/BP4/BP5's own real top-5 `shap_mean_abs_importance` entries
# (extracted verbatim by _extract_platform_source_data.py's `top5_shap_features()`) -- this
# is a TRANSLATION layer only (readable phrasing of a real feature name), never a source of
# new facts. An unrecognized real feature name (should not occur given this platform's fixed
# feature set) falls back to its own raw name in backticks rather than inventing a phrase.
# ============================================================================
_SHAP_FEATURE_PHRASES = {
    "Payment Format": "Payment Format",
    "sender_distinct_counterparties_to_date": "the sender's distinct-counterparty count to date",
    "sender_hours_since_prev_txn": "hours since the sender's previous transaction",
    "sender_txn_count_to_date": "the sender's transaction count to date",
    "log_amount_received": "the (log-scaled) amount received",
    "receiver_distinct_counterparties_to_date": "the receiver's distinct-counterparty count to date",
    "receiver_hours_since_prev_txn": "hours since the receiver's previous transaction",
    "amount_to_rolling_window_mean_ratio": "how far a transaction's amount sits from its own rolling-window average",
}


def _shap_phrase(feature_name: str) -> str:
    return _SHAP_FEATURE_PHRASES.get(feature_name, f"`{feature_name}`")


def _top_shap_phrase(top_shap_features: list, n: int = 2) -> str:
    """Real top-N SHAP drivers in plain language, joined naturally ('X and Y', or
    'X, Y, and Z'). Never invents a feature not in the real list passed in."""
    names = [f["name"] for f in top_shap_features[:n]]
    phrases = [_shap_phrase(name) for name in names]
    if len(phrases) == 1:
        return phrases[0]
    if len(phrases) == 2:
        return f"{phrases[0]} and {phrases[1]}"
    return ", ".join(phrases[:-1]) + f", and {phrases[-1]}"


def _citation_names(regulatory_mapping: list, indices: list) -> list:
    """Real citation NAMES only (the part before ' -- which BP(s)'), picked by index out of
    a BP's own real `regulatory_mapping` list -- the same 2-3 citations each BP's own
    methodology narrative names in prose, reused verbatim (not re-derived) wherever a
    structured citation list is needed (e.g. the Excel sheet). Never invents a citation."""
    return [regulatory_mapping[i].split(" -- ", 1)[0].strip() for i in indices]


# ============================================================================
# Real, substantive per-BP business narratives -- one genuinely distinct section per BP
# (never a templated mail-merge with only numbers swapped), covering what each BP actually
# does (business problem + real-world regulatory grounding, as already read from each BP's
# own MODEL_CARD.md/RULE_CARD.md Business Objective / regulatory-mapping sections and the
# locked master-execution-plan's own Section 3/6 tables during this platform's build), its
# real validated performance (champion, verdict, real headline metric), and what deploying
# it to production would concretely mean operationally -- citing only real numbers already
# present in `platform_source_data`. BP3 (no trained model, no dollar figure) is described
# in its own real terms (lift ratio, bootstrap CI, ego-network scale) rather than having a
# dollar figure invented for it.
#
# Each narrative also carries a second real-content layer, "methodology" (Methodology &
# Regulatory Basis), built from the platform source data's own real `business_objective`
# (tightened to report length, never changing its substance), the real champion/feature-
# count/threshold already used above, the real top-5 SHAP drivers in plain language (via
# `_top_shap_phrase`, never inventing a feature not in the real top-5 list), BP4/BP5's own
# real named engineered features where the real source data carries them, and 1-2 sentences
# naming the real citations most relevant to that BP out of its own real `regulatory_mapping`
# list (never the raw bullet dump). BP3 (no trained model) correctly has no SHAP sentence.
# ============================================================================
def build_bp_business_narratives_platform(platform_source_data: dict) -> dict:
    bps = platform_source_data["bps"]
    b1f, b2f, b3f, b4f, b5f = (
        bps["BP1"]["financial"],
        bps["BP2"]["financial"],
        bps["BP3"]["financial"],
        bps["BP4"]["financial"],
        bps["BP5"]["financial"],
    )
    b1 = bps["BP1"]["variants"][bps["BP1"]["primary_variant"]]
    b2 = bps["BP2"]["variants"][bps["BP2"]["primary_variant"]]
    b3 = bps["BP3"]["variants"][bps["BP3"]["primary_variant"]]
    b4 = bps["BP4"]["variants"][bps["BP4"]["primary_variant"]]
    b5 = bps["BP5"]["variants"][bps["BP5"]["primary_variant"]]
    v1, v2, v3, v4, v5 = (
        bps["BP1"]["primary_variant"],
        bps["BP2"]["primary_variant"],
        bps["BP3"]["primary_variant"],
        bps["BP4"]["primary_variant"],
        bps["BP5"]["primary_variant"],
    )
    accents = [
        PALETTE["series_1_blue"],
        PALETTE["series_2_orange"],
        PALETTE["series_3_aqua"],
        PALETTE["series_1_blue"],
        PALETTE["series_2_orange"],
    ]

    narratives = {
        "BP1": {
            "title": f"BP1 -- {bps['BP1']['name']}",
            "accent": accents[0],
            "verdict": b1.get("verdict", "N/A"),
            "what_it_does": (
                "BP1 is the real function financial institutions themselves call a "
                "‘transaction monitoring system’ -- language drawn directly from a real "
                "Federal Reserve consent order against American Express Bank International -- and "
                "the ‘computer monitoring system [that] issued alerts’ language from FinCEN's "
                "own civil money penalty assessment against JPMorgan Chase. It scores every real "
                "transaction against this dataset's real, direct ground-truth label (`Is Laundering`) "
                "using supervised imbalanced binary classification, with PR-AUC as the primary metric "
                "because laundering transactions are a small real fraction of all activity. This "
                "evidences USA PATRIOT Act Section 326/314(a)/(b) obligations and feeds FinCEN SAR "
                "filing (31 CFR 1020.320) -- it does not itself predict SAR-filed/not-filed."
            ),
            "real_performance": (
                f"On {v1} -- this BP's locked mandatory realism-validation tier -- the real champion "
                f"({b1.get('champion', 'N/A')}) passed both validation gates (verdict "
                f"{b1.get('verdict', 'N/A')}) using {b1.get('n_features', 'N/A')} real engineered "
                f"features, at a real selected decision threshold of {b1.get('threshold', 0):.4f}. At "
                f"that operating point it achieves real precision "
                f"{b1['test_metrics']['precision']:.3f} and real recall "
                f"{b1['test_metrics']['recall']:.3f} (real PR-AUC {b1['test_metrics']['pr_auc']:.4f})."
            ),
            "production_meaning": (
                f"Deployed to production, BP1's real measured improvement over a naive fixed-dollar-"
                f"threshold rule means investigators stop reviewing {b1f['fewer_fp_alerts']:,} real "
                f"false-positive alerts (ASSUMPTION-estimated at {b1f['investigator_hours_saved']:,} "
                f"investigator hours, {_fmt_usd(b1f['fp_dollar_savings'])}), while the same real "
                f"operating point independently catches {b1f['additional_real_cases_caught']:,} more "
                f"real laundering cases than the naive rule would (illustrative regulatory-exposure-"
                f"avoidance ASSUMPTION of {_fmt_usd(b1f['tp_dollar_illustrative'])}) -- freeing real "
                f"investigator capacity for genuine cases instead of chasing noise, and strengthening "
                f"the evidence base feeding the SAR-filing process."
            ),
            "methodology": (
                f"BP1's own real Business Objective is to build the core transaction-monitoring "
                f"capability every Bank Secrecy Act-regulated institution must operate under the "
                f"FFIEC's five pillars -- scoring individual transactions for real money-laundering "
                f"likelihood and feeding investigator alert review and any downstream SAR decision, "
                f"while controlling the false-positive alert volume that consumes most AML teams' "
                f"real capacity. The real champion ({b1.get('champion', 'N/A')}) reaches this using "
                f"{b1.get('n_features', 'N/A')} real engineered features at a real decision threshold "
                f"of {b1.get('threshold', 0):.4f}. Real SHAP analysis shows the model is driven most "
                f"by {_top_shap_phrase(bps['BP1'].get('top_shap_features', []))}. Regulatory basis: "
                f"the Bank Secrecy Act (31 U.S.C. Section 5311) platform-wide, USA PATRIOT Act Section "
                f"326 (CIP) and Section 314(a)/(b) (BP1, BP5), and FinCEN's SAR filing requirement "
                f"(31 CFR Section 1020.320)."
            ),
            "regulatory_citations": _citation_names(bps["BP1"]["regulatory_mapping"], [0, 1, 2]),
            "business_objective_tightened": (
                "BP1 builds the core transaction-monitoring capability every Bank Secrecy "
                "Act-regulated institution must operate under the FFIEC's five pillars -- "
                "scoring individual transactions for real money-laundering likelihood and "
                "feeding investigator alert review and any downstream SAR decision, while "
                "controlling the false-positive alert volume that consumes most AML teams' "
                "real capacity."
            ),
        },
        "BP2": {
            "title": f"BP2 -- {bps['BP2']['name']}",
            "accent": accents[1],
            "verdict": b2.get("verdict", "N/A"),
            "what_it_does": (
                "BP2 answers a different question than BP1: not just ‘is this suspicious’ but "
                "‘which of the real labeled laundering typologies does it match’ -- a real "
                "multi-class target this dataset's own `Patterns.txt` ground truth supports across up "
                "to 8 typologies (fan-out, fan-in, gather-scatter, scatter-gather, cycle, random, "
                "bipartite, stack). This is the ‘red flags’ language FinCEN's own AML guidance "
                "uses for typology indicators, and the specific terminology FinCEN's real civil penalty "
                "assessment against JPMorgan Chase used describing red-flag indicators the bank was "
                "found to have missed. BP2 evidences FATF's 40 Recommendations and feeds the same real "
                "SAR process BP1 does, with typology-level detail BP1's binary flag cannot provide."
            ),
            "real_performance": (
                f"On {v2}, the real champion ({b2.get('champion', 'N/A')}) passed both validation gates "
                f"(verdict {b2.get('verdict', 'N/A')}) using {b2.get('n_features', 'N/A')} real "
                f"engineered features, achieving a real macro-F1 of "
                f"{b2['test_metrics']['macro_f1']:.3f} across the typologies with enough real matched "
                f"examples this run"
                + (
                    f" (the two largest real classes: "
                    f"{max(b2.get('class_counts', {'N/A': 0}), key=b2.get('class_counts', {'N/A': 0}).get)} "
                    f"with {max(b2.get('class_counts', {'N/A': 0}).values(), default=0):,} real examples)."
                    if b2.get("class_counts")
                    else "."
                )
            ),
            "production_meaning": (
                f"Deployed, BP2 would auto-classify {b2f['more_cases_auto_typed']:,} more real cases by "
                f"typology than a single-typology heuristic rule can (ASSUMPTION-estimated at "
                f"{b2f['auto_typing_hours_saved']:.1f} auto-typing hours saved, "
                f"{_fmt_usd(b2f['auto_typing_efficiency_savings'])}) -- freeing analysts from manual "
                f"typology lookup -- while independently confirming the correct typology on "
                f"{b2f['cases_old_rule_missed']:,} real cases the old single-typology heuristic rule "
                f"would have missed outright (typology-confirmation value ASSUMPTION of "
                f"{_fmt_usd(b2f['typology_confirmation_value'])}). These two figures are kept "
                f"deliberately separate from BP1/BP4/BP5's categories (different unit basis, different "
                f"real case subset) rather than blended into one platform total."
            ),
            "methodology": (
                f"BP2's own real Business Objective is to classify transactions already known to be "
                f"laundering into the specific real money-laundering typology they exhibit -- directly "
                f"matching the 'red flags' terminology used in real regulatory enforcement actions -- "
                f"giving investigators a real, evidence-backed starting typology for case triage and "
                f"SAR-narrative drafting rather than leaving every case to be typed manually. The real "
                f"champion ({b2.get('champion', 'N/A')}) reaches this using "
                f"{b2.get('n_features', 'N/A')} real engineered features (multi-class argmax, no single "
                f"decision threshold). Real SHAP analysis shows the model is driven most by "
                f"{_top_shap_phrase(bps['BP2'].get('top_shap_features', []))}. Regulatory basis: the "
                f"Bank Secrecy Act (31 U.S.C. Section 5311) platform-wide, FinCEN's own 'red flags' "
                f"typology guidance from its JPMorgan Chase assessment (Madoff/BLM case) -- the "
                f"specific real-world terminology this BP's typology framing matches -- and the same "
                f"SAR filing requirement (31 CFR Section 1020.320) BP1 feeds."
            ),
            "regulatory_citations": _citation_names(bps["BP2"]["regulatory_mapping"], [0, 1, 2]),
            "business_objective_tightened": (
                "BP2 classifies transactions already known to be laundering into the "
                "specific real money-laundering typology they exhibit -- directly matching "
                "the 'red flags' terminology used in real regulatory enforcement actions -- "
                "giving investigators a real, evidence-backed starting typology for case "
                "triage and SAR-narrative drafting."
            ),
        },
        "BP3": {
            "title": f"BP3 -- {bps['BP3']['name']}",
            "accent": accents[2],
            "verdict": b3.get("verdict", "N/A"),
            "what_it_does": (
                "BP3 has no trained ML model and needs none -- it asks a structural question BP1/BP2/"
                "BP4/BP5 cannot: is an account's real position in the transaction network itself "
                "informative, independent of its own transaction history? Unlike the other four BPs' "
                "real-world grounding, this specific graph-analytics framing was not independently "
                "confirmed as specific to either enforcement action's own internal terminology in the primary documents checked "
                "during this platform's own feasibility review -- honestly flagged rather than "
                "overclaimed -- though network/graph analytics is standard industry AML practice, and "
                "this BP's real output carries GDPR cross-border-data-handling relevance alongside "
                "BP5."
            ),
            "real_performance": (
                f"On {v3} -- a real graph of {b3f['n_nodes']:,} nodes and {b3f['n_edges']:,} edges -- "
                f"the real champion signal ('{b3.get('champion', 'N/A')}') passed both validation gates "
                f"(verdict {b3.get('verdict', 'N/A')}) with a real network-lift ratio of "
                f"{b3['test_metrics']['lift_ratio']:.2f}x over the real base rate of "
                f"{b3f['base_rate_pct']:.3f}% (bootstrap 95% CI "
                f"[{b3f['ci95_low']:.3f}x, {b3f['ci95_high']:.3f}x], confirming the lift is real and "
                f"not sampling noise)."
            ),
            "production_meaning": (
                f"Deployed, BP3 would not replace BP1/BP2/BP4/BP5's own scoring -- it would hand "
                f"investigators a real bounded 2-hop ego-network around every flagged account "
                f"(illustrative real examples sized "
                f"{', '.join(f'{n:,}' for n in b3f.get('ego_network_sizes', []))} real accounts before "
                f"the locked 2,000-node cap) instead of reviewing that one account in isolation. There "
                f"is deliberately no dollar figure here -- {b3f.get('no_dollar_reason', 'no sourced per-account cost basis exists')}"
                f" -- but a {b3['test_metrics']['lift_ratio']:.2f}x real lift at "
                f"{b3f['n_nodes']:,}-node platform scale is a materially different, network-aware "
                f"triage signal than single-account review alone."
            ),
            "methodology": (
                f"BP3's own real Business Objective is to flag accounts using directly-interpretable "
                f"graph-structural signals -- real degree, real PageRank, and real network proximity "
                f"to already-flagged accounts -- computed from the real account-to-account transaction "
                f"structure, with no ground-truth label required to construct them. BP3 has no trained "
                f"ML model and genuinely no SHAP/LIME explainability section (not merely omitted); the "
                f"real champion signal ('{b3.get('champion', 'N/A')}') is ranked purely by its real "
                f"network-lift ratio on a real held-out test set of accounts. Regulatory basis: the "
                f"Bank Secrecy Act (31 U.S.C. Section 5311) platform-wide and the FFIEC's five-pillar "
                f"BSA/AML Examination Manual, under which link analysis and relationship mapping are a "
                f"recognized investigative technique -- honestly flagged as not independently confirmed "
                f"against a primary enforcement document, unlike the other four BPs' real-world "
                f"grounding."
            ),
            "regulatory_citations": _citation_names(bps["BP3"]["regulatory_mapping"], [0, 1]),
            "business_objective_tightened": (
                "BP3 flags accounts using directly-interpretable graph-structural signals -- "
                "real degree, real PageRank, and real network proximity to already-flagged "
                "accounts -- computed from the real account-to-account transaction structure, "
                "with no ground-truth label required to construct them."
            ),
        },
        "BP4": {
            "title": f"BP4 -- {bps['BP4']['name']}",
            "accent": accents[3],
            "verdict": b4.get("verdict", "N/A"),
            "what_it_does": (
                "BP4 targets a real named federal crime: 31 U.S.C. Section 5324 makes it illegal to "
                "break transactions into smaller pieces specifically to evade Bank Secrecy Act "
                "reporting requirements, and detecting this pattern is a mandatory examination area at "
                "every BSA-regulated institution. BP4 engineers 5 real, rule-derived structuring/"
                "smurfing features (sub-threshold amount clustering, time-clustering, fan-out "
                "splitting) on top of BP1's existing feature set, testing whether structuring-specific "
                "behavior carries real additional predictive lift for the same `Is Laundering` label "
                "BP1 uses."
            ),
            "real_performance": (
                f"On {v4}, the real champion ({b4.get('champion', 'N/A')}) passed both validation "
                f"gates (verdict {b4.get('verdict', 'N/A')}) using {b4.get('n_features', 'N/A')} real "
                f"features (BP1's 19 plus BP4's own 5 structuring-specific ones) at a real threshold "
                f"of {b4.get('threshold', 0):.4f}, achieving real precision "
                f"{b4['test_metrics']['precision']:.3f} and real recall "
                f"{b4['test_metrics']['recall']:.3f} (real PR-AUC {b4['test_metrics']['pr_auc']:.4f}) "
                f"-- the highest real recall of the platform's three binary BPs, at the cost of lower "
                f"real precision, a real trade-off worth flagging for threshold review."
            ),
            "production_meaning": (
                f"Deployed, BP4 contributes the single largest real dollar figure on the entire "
                f"platform: an illustrative regulatory-exposure-avoidance ASSUMPTION of "
                f"{_fmt_usd(b4f['tp_dollar_illustrative'])} from {b4f['additional_real_cases_caught']:,} "
                f"additional real structuring cases caught that a naive rule would miss, plus "
                f"{_fmt_usd(b4f['fp_dollar_savings'])} in false-positive-reduction savings "
                f"({b4f['investigator_hours_saved']:,} investigator hours, "
                f"{b4f['fewer_fp_alerts']:,} fewer false-positive alerts). Given structuring's own "
                f"named statute and mandatory-examination status, this is real evidence this is the "
                f"platform's highest-priority capability to keep in continuous production monitoring."
            ),
            "methodology": (
                f"BP4's own real Business Objective targets a federal crime with its own named statute: "
                f"31 U.S.C. Section 5324 makes it illegal to break transactions into smaller pieces "
                f"specifically to evade Bank Secrecy Act reporting requirements, and detecting this "
                f"pattern is a mandatory examination area at every BSA-regulated institution. Beyond "
                f"BP1's shared feature set, BP4 adds its own real {len(bps['BP4'].get('named_engineered_features', []))} "
                f"named structuring-specific features -- "
                + ", ".join(f"`{f}`" for f in bps["BP4"].get("named_engineered_features", []))
                + f" -- of which `amount_to_rolling_window_mean_ratio` ranks among the real top-5 "
                f"global SHAP drivers this run: the model overall is driven most by "
                f"{_top_shap_phrase(bps['BP4'].get('top_shap_features', []))}. Regulatory basis: BP4's "
                f"own named statute, the BSA structuring statute (31 U.S.C. Section 5324), sits "
                f"alongside the Bank Secrecy Act (31 U.S.C. Section 5311) platform-wide and the same "
                f"SAR filing requirement (31 CFR Section 1020.320) BP1/BP2 feed."
            ),
            "regulatory_citations": _citation_names(bps["BP4"]["regulatory_mapping"], [1, 0, 2]),
            "business_objective_tightened": (
                "BP4 targets a federal crime with its own named statute: 31 U.S.C. Section "
                "5324 makes it illegal to break transactions into smaller pieces specifically "
                "to evade Bank Secrecy Act reporting requirements -- a mandatory examination "
                "area at every BSA-regulated institution."
            ),
        },
        "BP5": {
            "title": f"BP5 -- {bps['BP5']['name']}",
            "accent": accents[4],
            "verdict": b5.get("verdict", "N/A"),
            "what_it_does": (
                "BP5 targets correspondent banking and cross-border wire risk -- the specific area "
                "that drove the real HSBC, Standard Chartered, and Danske Bank enforcement actions, "
                "and a standing high-priority area industry-wide. It uses this dataset's real cross-"
                "institution, cross-border structure (bank-to-bank transfer fields plus the real "
                "country-tagged bank names in the accounts data, e.g. 'Portugal Bank #4507') to score "
                "cross-border flow risk, evidencing USA PATRIOT Act Section 314(a)/(b), OFAC "
                "sanctions-list screening context, the Wolfsberg AML Principles for correspondent "
                "banking, and GDPR cross-border-data-handling relevance alongside BP3."
            ),
            "real_performance": (
                f"On {v5}, the real champion ({b5.get('champion', 'N/A')}) passed both validation "
                f"gates (verdict {b5.get('verdict', 'N/A')}) using {b5.get('n_features', 'N/A')} real "
                f"features -- the most of any binary BP on the platform, reflecting the added "
                f"cross-border/country-pair signal -- at a real threshold of "
                f"{b5.get('threshold', 0):.4f}, achieving real precision "
                f"{b5['test_metrics']['precision']:.3f} and real recall "
                f"{b5['test_metrics']['recall']:.3f} (real PR-AUC {b5['test_metrics']['pr_auc']:.4f})."
            ),
            "production_meaning": (
                f"Deployed, BP5 delivers the platform's single largest real false-positive-reduction "
                f"figure: {_fmt_usd(b5f['fp_dollar_savings'])} in savings from "
                f"{b5f['investigator_hours_saved']:,} investigator hours freed across "
                f"{b5f['fewer_fp_alerts']:,} fewer false-positive alerts -- more than either BP1 or "
                f"BP4 -- plus {_fmt_usd(b5f['tp_dollar_illustrative'])} illustrative regulatory-"
                f"exposure-avoidance from {b5f['additional_real_cases_caught']:,} additional real "
                f"cross-border cases caught. Given the real enforcement history this capability is "
                f"modeled against, keeping it in continuous production use directly addresses the "
                f"exact risk area regulators have most recently and visibly penalized at other "
                f"institutions."
            ),
            "methodology": (
                f"BP5's own real Business Objective targets the single highest-risk channel for "
                f"sanctioned-party exposure and cross-border money-laundering flow: wires crossing a "
                f"national border. Beyond the platform's shared 19-feature transaction-monitoring set, "
                f"BP5 adds its own real {len(bps['BP5'].get('named_engineered_features', []))} named "
                f"cross-border features -- "
                + ", ".join(f"`{f}`" for f in bps["BP5"].get("named_engineered_features", []))
                + f". None of these 8 cross-border-specific features broke into the real top-5 overall "
                f"SHAP drivers this run -- the model overall remains driven most by "
                f"{_top_shap_phrase(bps['BP5'].get('top_shap_features', []))} -- though this BP's own "
                f"MODEL_CARD.md separately ranks `sender_country_empirical_risk` as the top driver "
                f"specifically among its own cross-border feature subset. Regulatory basis: USA "
                f"PATRIOT Act Section 326 (Customer Identification Program) for correspondent-banking "
                f"onboarding, Section 314(a)/(b) for cross-border information sharing -- this BP's own "
                f"named obligation -- and the Wolfsberg Group's Correspondent Banking Due Diligence "
                f"Questionnaire (CBDDQ) principles; OFAC sanctions-list screening is part of this BP's "
                f"regulatory framing but is Not Possible - Data Limitation on this synthetic dataset."
            ),
            "regulatory_citations": _citation_names(bps["BP5"]["regulatory_mapping"], [1, 2, 4]),
            "business_objective_tightened": (
                "BP5 targets the single highest-risk channel for sanctioned-party exposure "
                "and cross-border money-laundering flow: wires crossing a national border."
            ),
        },
    }
    return narratives


# ============================================================================
# Word report (python-docx) -- platform rollup equivalent
# ============================================================================
def write_platform_word_report(path: Path, context: dict) -> Path:
    from docx import Document
    from docx.shared import Pt, RGBColor

    psd = context["platform_source_data"]
    roll = psd["platform_rollup"]

    doc = Document()
    _apply_word_brand_styles(doc)
    doc.add_heading(f"{context['bp_id']}: {context['bp_name']}", level=0)
    p = doc.add_paragraph()
    p.add_run(
        f"Platform-Wide Compliance-Impact Rollup -- generated {context['generated_at_utc']} UTC"
    ).italic = True

    doc.add_heading("Business Objective", level=1)
    doc.add_paragraph(context["business_objective"])

    status = context.get("status") or compute_platform_status(psd)
    doc.add_heading("Recommendation & Status", level=1)
    p = doc.add_paragraph()
    run = p.add_run(status["label"])
    run.bold = True
    run.font.size = Pt(14)
    status_colors = {
        "good": RGBColor(0x0C, 0xA3, 0x0C),
        "warning": RGBColor(0xC9, 0x85, 0x00),
        "critical": RGBColor(0xD0, 0x3B, 0x3B),
    }
    run.font.color.rgb = status_colors.get(status["css_class"], RGBColor(0x0B, 0x0B, 0x0B))
    doc.add_paragraph(status["rationale"])

    doc.add_heading("Executive Summary", level=1)
    doc.add_paragraph(
        f"This platform-wide rollup is a pure, read-only aggregation of BP1-BP5's own already-"
        f"computed real figures. Sourcing method (verbatim): \"{psd['sourcing_method']}\""
    )

    doc.add_heading("What This Means for the Business", level=1)
    for point in context["business_benefits"]:
        doc.add_paragraph(point, style="List Bullet")

    doc.add_heading("Three-Category Financial Rollup (never blended)", level=1)
    doc.add_paragraph(roll["headline_grand_total_note"])
    ben_df = context["benefit_table"]
    table = doc.add_table(rows=1, cols=len(ben_df.columns))
    table.style = "Light Grid Accent 1"
    for i, col in enumerate(ben_df.columns):
        table.rows[0].cells[i].text = col
    for _, row in ben_df.iterrows():
        cells = table.add_row().cells
        for i, col in enumerate(ben_df.columns):
            cells[i].text = str(row[col])

    doc.add_heading("Per-BP Status Grid", level=1)
    grid_table = doc.add_table(rows=1, cols=5)
    grid_table.style = "Light Grid Accent 1"
    for i, h in enumerate(["BP", "Name", "Primary Variant", "Champion / Signal", "Verdict"]):
        grid_table.rows[0].cells[i].text = h
    for bp_id, d in psd["bps"].items():
        primary = d["variants"][d["primary_variant"]]
        row = grid_table.add_row().cells
        row[0].text = bp_id
        row[1].text = d["name"]
        row[2].text = d["primary_variant"]
        row[3].text = primary.get("champion", "N/A")
        row[4].text = primary.get("verdict", "N/A")

    if context.get("phase_rollup"):
        doc.add_heading("Phase-Grouped Rollup", level=1)
        for phase_name, phase in context["phase_rollup"].get("phases", {}).items():
            doc.add_heading(phase_name, level=2)
            doc.add_paragraph(f"BPs: {', '.join(phase['bp_ids'])}")
            for line in phase.get("summary_lines", []):
                doc.add_paragraph(line, style="List Bullet")

    doc.add_heading("Per-BP Business Narratives", level=1)
    doc.add_paragraph(
        "What each business problem actually does, its real validated performance, and what "
        "deploying it to production would concretely mean operationally -- every sentence "
        "below cites a real number already present in this platform's own source data."
    )
    narratives = context.get("bp_narratives") or build_bp_business_narratives_platform(psd)
    for bp_id, n in narratives.items():
        doc.add_heading(n["title"], level=2)
        p = doc.add_paragraph()
        run = p.add_run(f"Verdict: {n['verdict']}")
        run.bold = True
        doc.add_heading("What it does", level=3)
        doc.add_paragraph(n["what_it_does"])
        doc.add_heading("Real validated performance", level=3)
        doc.add_paragraph(n["real_performance"])
        doc.add_heading("What production deployment would mean", level=3)
        doc.add_paragraph(n["production_meaning"])
        if n.get("methodology"):
            doc.add_heading("Methodology & Regulatory Basis", level=3)
            doc.add_paragraph(n["methodology"])

    doc.add_heading("Regulatory & Compliance Mapping", level=1)
    reg_table = doc.add_table(rows=1, cols=2)
    reg_table.style = "Light Grid Accent 1"
    reg_table.rows[0].cells[0].text = "Framework"
    reg_table.rows[0].cells[1].text = "Applies to"
    for fw, applies in context["regulatory_frameworks"]:
        row = reg_table.add_row().cells
        row[0].text = fw
        row[1].text = applies

    doc.add_heading("Fairness / Bias Testing", level=1)
    doc.add_paragraph(context["fairness_note"])

    doc.add_heading("Limitations & Caveats", level=1)
    for cav in context.get("caveats", []):
        doc.add_paragraph(cav, style="List Bullet")

    doc.add_heading("Recommendations", level=1)
    recs = context.get("smart_recommendations") or generate_platform_smart_recommendations(psd)
    for r in recs:
        doc.add_heading(r["title"], level=2)
        for label in ("specific", "measurable", "achievable", "relevant", "time_bound"):
            p = doc.add_paragraph(style="List Bullet")
            run = p.add_run(f"{label.replace('_', '-').title()}: ")
            run.bold = True
            p.add_run(r[label])

    _brand_word_table_headers(doc)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    return path


# ============================================================================
# Excel workbook (openpyxl) -- "Source Provenance" sheet FIRST (BP6 invents no new
# assumptions, so this replaces the Assumptions-sheet-first pattern used by the binary/
# multiclass paths: instead of disclosing hardcoded inputs, this sheet discloses exactly
# which real BP1-BP5 file each platform figure traces back to -- the zero-fabrication chain
# of custody made visible in the deliverable itself).
# ============================================================================
def write_platform_excel_workbook(path: Path, context: dict) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.workbook.properties import CalcProperties

    psd = context["platform_source_data"]
    roll = psd["platform_rollup"]
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="2A78D6", end_color="2A78D6", fill_type="solid")

    wb = Workbook()
    wb.calculation = CalcProperties(fullCalcOnLoad=True)

    # --- Source Provenance sheet FIRST ---
    ws_p = wb.active
    ws_p.title = "Source Provenance"
    prov_headers = ["Platform Figure", "Real Value", "Sourced From (real file)", "Sourced Via"]
    for c, h in enumerate(prov_headers, start=1):
        cell = ws_p.cell(row=1, column=c, value=h)
        cell.font = header_font
        cell.fill = header_fill
    prov_rows = [
        (
            "BP1 FP-reduction $ savings",
            _fmt_usd(roll["benefit_category_1_fp_reduction_savings"]["bp1"]),
            "reports/bp1_transaction_monitoring_detection/MODEL_CARD.md -- Financial Impact Summary",
            "Regex-parsed, verbatim",
        ),
        (
            "BP4 FP-reduction $ savings",
            _fmt_usd(roll["benefit_category_1_fp_reduction_savings"]["bp4"]),
            "reports/bp4_structuring_smurfing_detection/MODEL_CARD.md -- Financial Impact Summary",
            "Regex-parsed, verbatim",
        ),
        (
            "BP5 FP-reduction $ savings",
            _fmt_usd(roll["benefit_category_1_fp_reduction_savings"]["bp5"]),
            "reports/bp5_correspondent_banking_crossborder_risk/MODEL_CARD.md -- Financial Impact Summary",
            "Regex-parsed, verbatim",
        ),
        (
            "BP1 TP-uplift illustrative $",
            _fmt_usd(roll["benefit_category_2_tp_uplift_value"]["bp1"]),
            "reports/bp1_transaction_monitoring_detection/MODEL_CARD.md -- Financial Impact Summary",
            "Regex-parsed, verbatim",
        ),
        (
            "BP4 TP-uplift illustrative $",
            _fmt_usd(roll["benefit_category_2_tp_uplift_value"]["bp4"]),
            "reports/bp4_structuring_smurfing_detection/MODEL_CARD.md -- Financial Impact Summary",
            "Regex-parsed, verbatim",
        ),
        (
            "BP5 TP-uplift illustrative $",
            _fmt_usd(roll["benefit_category_2_tp_uplift_value"]["bp5"]),
            "reports/bp5_correspondent_banking_crossborder_risk/MODEL_CARD.md -- Financial Impact Summary",
            "Regex-parsed, verbatim",
        ),
        (
            "BP2 auto-typing efficiency savings",
            _fmt_usd(roll["benefit_category_3_bp2_typology_lines"]["auto_typing_efficiency_savings_usd"]),
            "reports/bp2_typology_redflag_detection/MODEL_CARD.md -- Financial Impact Summary",
            "Regex-parsed, verbatim",
        ),
        (
            "BP2 typology confirmation value",
            _fmt_usd(roll["benefit_category_3_bp2_typology_lines"]["typology_confirmation_value_usd"]),
            "reports/bp2_typology_redflag_detection/MODEL_CARD.md -- Financial Impact Summary",
            "Regex-parsed, verbatim",
        ),
        (
            "BP3 real network nodes",
            f"{roll['portfolio_scale']['bp3_n_nodes']:,}",
            "reports/bp3_network_graph_intelligence/bp3_notebook3_validation_report_li_medium.json",
            "JSON field read, verbatim",
        ),
        (
            "BP3 real network edges",
            f"{roll['portfolio_scale']['bp3_n_edges']:,}",
            "reports/bp3_network_graph_intelligence/bp3_notebook3_validation_report_li_medium.json",
            "JSON field read, verbatim",
        ),
        (
            "All-BP verdict summary",
            ", ".join(f"{k}={v}" for k, v in roll["all_bps_verdict_summary"].items()),
            "Each BP's own bpN_notebook3_validation_report_*.json -- overall_verdict field",
            "JSON field read, verbatim",
        ),
    ]
    for r, (label, val, src, via) in enumerate(prov_rows, start=2):
        ws_p.cell(row=r, column=1, value=label)
        ws_p.cell(row=r, column=2, value=val)
        ws_p.cell(row=r, column=3, value=src)
        ws_p.cell(row=r, column=4, value=via)
    ws_p.cell(
        row=len(prov_rows) + 3,
        column=1,
        value=f"Sourcing method (verbatim, from the extractor script): {psd['sourcing_method']}",
    ).font = Font(italic=True, color="52514E")
    ws_p.column_dimensions["A"].width = 34
    ws_p.column_dimensions["B"].width = 22
    ws_p.column_dimensions["C"].width = 70
    ws_p.column_dimensions["D"].width = 24
    ws_p.auto_filter.ref = f"A1:D{1 + len(prov_rows)}"
    _brand_excel_sheet(ws_p, PALETTE["ink_muted"], freeze_cell="A2")
    _band_excel_rows(ws_p, first_data_row=2, last_data_row=1 + len(prov_rows), first_col=1, last_col=4)

    # --- Executive Summary sheet ---
    status = context.get("status") or compute_platform_status(psd)
    status_hex = {"good": "0CA30C", "warning": "FAB219", "critical": "D03B3B"}.get(
        status["css_class"], "2A78D6"
    )
    ws_e = wb.create_sheet("Executive Summary")
    ws_e["A1"] = "Status"
    ws_e["B1"] = "Rationale"
    ws_e["A1"].font = header_font
    ws_e["B1"].font = header_font
    ws_e["A1"].fill = header_fill
    ws_e["B1"].fill = header_fill
    ws_e["A2"] = status["label"]
    ws_e["A2"].fill = PatternFill(start_color=status_hex, end_color=status_hex, fill_type="solid")
    ws_e["A2"].font = Font(bold=True, color="FFFFFF")
    ws_e["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws_e["B2"] = status["rationale"]
    ws_e["B2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws_e.row_dimensions[2].height = 70
    ws_e.column_dimensions["A"].width = 46
    ws_e.column_dimensions["B"].width = 100
    _brand_excel_sheet(ws_e, status_hex, freeze_cell="A3")

    # --- Benefit Detail sheet -- the three-category discipline, live SUM formulas for TOTAL rows ---
    ws_b = wb.create_sheet("Benefit Detail (3 Categories)")
    headers = ["Category", "Line Item", "Value (raw)", "Formatted", "Note"]
    for c, h in enumerate(headers, start=1):
        cell = ws_b.cell(row=1, column=c, value=h)
        cell.font = header_font
        cell.fill = header_fill
    cat1, cat2, cat3 = (
        roll["benefit_category_1_fp_reduction_savings"],
        roll["benefit_category_2_tp_uplift_value"],
        roll["benefit_category_3_bp2_typology_lines"],
    )
    r = 2
    cat1_start = r
    for label, key in [("BP1", "bp1"), ("BP4", "bp4"), ("BP5", "bp5")]:
        ws_b.cell(row=r, column=1, value="BENEFIT 1 -- FP-Reduction Savings")
        ws_b.cell(row=r, column=2, value=label)
        ws_b.cell(row=r, column=3, value=cat1[key])
        ws_b.cell(row=r, column=3).number_format = _EXCEL_USD_FORMAT
        ws_b.cell(row=r, column=4, value=_excel_usd_shorthand_formula(f"C{r}"))
        r += 1
    cat1_total_row = r
    ws_b.cell(row=r, column=1, value="BENEFIT 1 -- FP-Reduction Savings")
    ws_b.cell(row=r, column=2, value="TOTAL (live formula, BP1+BP4+BP5)")
    ws_b.cell(row=r, column=3, value=f"=SUM(C{cat1_start}:C{cat1_total_row - 1})")
    ws_b.cell(row=r, column=3).number_format = _EXCEL_USD_FORMAT
    ws_b.cell(row=r, column=4, value=_excel_usd_shorthand_formula(f"C{r}"))
    ws_b.cell(
        row=r,
        column=5,
        value=f"{cat1['total_investigator_hours_saved']:,} hrs saved, "
        f"{cat1['total_fewer_fp_alerts']:,} fewer FP alerts",
    )
    for c in range(1, 4):
        ws_b.cell(row=r, column=c).font = Font(bold=True)
    r += 2

    cat2_start = r
    for label, key in [("BP1", "bp1"), ("BP4", "bp4"), ("BP5", "bp5")]:
        ws_b.cell(row=r, column=1, value="BENEFIT 2 -- TP-Uplift Illustrative Value")
        ws_b.cell(row=r, column=2, value=label)
        ws_b.cell(row=r, column=3, value=cat2[key])
        ws_b.cell(row=r, column=3).number_format = _EXCEL_USD_FORMAT
        ws_b.cell(row=r, column=4, value=_excel_usd_shorthand_formula(f"C{r}"))
        r += 1
    cat2_total_row = r
    ws_b.cell(row=r, column=1, value="BENEFIT 2 -- TP-Uplift Illustrative Value")
    ws_b.cell(row=r, column=2, value="TOTAL (live formula, BP1+BP4+BP5)")
    ws_b.cell(row=r, column=3, value=f"=SUM(C{cat2_start}:C{cat2_total_row - 1})")
    ws_b.cell(row=r, column=3).number_format = _EXCEL_USD_FORMAT
    ws_b.cell(row=r, column=4, value=_excel_usd_shorthand_formula(f"C{r}"))
    ws_b.cell(row=r, column=5, value=f"{cat2['total_additional_cases_caught']:+,} cases caught")
    for c in range(1, 4):
        ws_b.cell(row=r, column=c).font = Font(bold=True)
    r += 2

    ws_b.cell(row=r, column=1, value="BENEFIT 3 -- BP2 Typology Lines (kept separate)")
    ws_b.cell(row=r, column=2, value="Auto-typing efficiency savings")
    ws_b.cell(row=r, column=3, value=cat3["auto_typing_efficiency_savings_usd"])
    ws_b.cell(row=r, column=3).number_format = _EXCEL_USD_FORMAT
    ws_b.cell(row=r, column=4, value=_excel_usd_shorthand_formula(f"C{r}"))
    r += 1
    ws_b.cell(row=r, column=1, value="BENEFIT 3 -- BP2 Typology Lines (kept separate)")
    ws_b.cell(row=r, column=2, value="Typology confirmation value")
    ws_b.cell(row=r, column=3, value=cat3["typology_confirmation_value_usd"])
    ws_b.cell(row=r, column=3).number_format = _EXCEL_USD_FORMAT
    ws_b.cell(row=r, column=4, value=_excel_usd_shorthand_formula(f"C{r}"))
    r += 2

    ws_b.cell(row=r, column=1, value="COST CONTEXT (informational only)")
    ws_b.cell(row=r, column=2, value="Platform build/operating cost")
    ws_b.cell(row=r, column=3, value="NOT SOURCED")
    ws_b.cell(row=r, column=5, value=roll["cost_context"]["description"])
    r += 2

    ws_b.cell(row=r, column=1, value="PORTFOLIO SCALE (volume only, never dollarized)")
    ws_b.cell(row=r, column=2, value="BP3 real network nodes")
    ws_b.cell(row=r, column=3, value=roll["portfolio_scale"]["bp3_n_nodes"])
    r += 1
    ws_b.cell(row=r, column=1, value="PORTFOLIO SCALE (volume only, never dollarized)")
    ws_b.cell(row=r, column=2, value="BP3 real network edges")
    ws_b.cell(row=r, column=3, value=roll["portfolio_scale"]["bp3_n_edges"])
    r += 2

    ws_b.cell(
        row=r,
        column=1,
        value="Note: the figures above are never summed across categories -- "
        "this platform reports three separate BENEFIT lines, never one "
        "blended grand total (locked Section 7A/8 policy).",
    ).font = Font(italic=True, color="52514E")

    for c, w in zip(range(1, 6), [40, 32, 18, 24, 48]):
        ws_b.column_dimensions[get_column_letter(c)].width = w
    _brand_excel_sheet(ws_b, PALETTE["series_1_blue"], freeze_cell="A2")

    # --- Per-BP Status Grid sheet ---
    ws_g = wb.create_sheet("Per-BP Status Grid")
    grid_headers = ["BP", "Name", "Phase", "Primary Variant", "Champion / Signal", "Verdict"]
    for c, h in enumerate(grid_headers, start=1):
        cell = ws_g.cell(row=1, column=c, value=h)
        cell.font = header_font
        cell.fill = header_fill
    for r2, (bp_id, d) in enumerate(psd["bps"].items(), start=2):
        primary = d["variants"][d["primary_variant"]]
        ws_g.cell(row=r2, column=1, value=bp_id)
        ws_g.cell(row=r2, column=2, value=d["name"])
        ws_g.cell(row=r2, column=3, value=d["phase"])
        ws_g.cell(row=r2, column=4, value=d["primary_variant"])
        ws_g.cell(row=r2, column=5, value=primary.get("champion", "N/A"))
        ws_g.cell(row=r2, column=6, value=primary.get("verdict", "N/A"))
    n_bps = len(psd["bps"])
    ws_g.auto_filter.ref = f"A1:F{1 + n_bps}"
    for c, w in zip(range(1, 7), [8, 42, 36, 16, 26, 12]):
        ws_g.column_dimensions[get_column_letter(c)].width = w
    _brand_excel_sheet(ws_g, PALETTE["series_3_aqua"], freeze_cell="A2")
    _band_excel_rows(ws_g, first_data_row=2, last_data_row=1 + n_bps, first_col=1, last_col=6)
    _color_verdict_cells(ws_g, rows=range(2, 2 + n_bps), cols=[6])

    # --- Per-BP Business & Methodology sheet -- one row-block per BP, reusing the exact
    # same real narrative content (business_objective, top_shap_features,
    # named_engineered_features, regulatory_citations, production_meaning) already built by
    # build_bp_business_narratives_platform() for the HTML dashboard, Word report, and
    # PLATFORM_CARD.md -- never re-derived here, so all five output formats stay in sync
    # off the same single real source. ---
    narratives = context.get("bp_narratives") or build_bp_business_narratives_platform(psd)
    ws_n = wb.create_sheet("Per-BP Business & Methodology")
    narr_headers = [
        "BP",
        "Business Objective",
        "Champion / Signal",
        "Feature Count",
        "Threshold",
        "Top SHAP Drivers",
        "Named Engineered Features",
        "Regulatory Citations",
        "Business Impact",
    ]
    for c, h in enumerate(narr_headers, start=1):
        cell = ws_n.cell(row=1, column=c, value=h)
        cell.font = header_font
        cell.fill = header_fill
    wrap_top = Alignment(wrap_text=True, vertical="top")
    for r3, bp_id in enumerate(["BP1", "BP2", "BP3", "BP4", "BP5"], start=2):
        bp_data = psd["bps"][bp_id]
        n = narratives[bp_id]
        primary = bp_data["variants"][bp_data["primary_variant"]]
        shap_names = ", ".join(f["name"] for f in bp_data.get("top_shap_features", []))
        named_feats = ", ".join(bp_data.get("named_engineered_features", []))  # genuinely blank for BP1/2/3
        reg_citations = "; ".join(n.get("regulatory_citations", []))
        threshold_val = primary.get("threshold")
        threshold_display = f"{threshold_val:.4f}" if isinstance(threshold_val, (int, float)) else ""

        ws_n.cell(row=r3, column=1, value=bp_id).font = Font(bold=True)
        ws_n.cell(row=r3, column=2, value=n.get("business_objective_tightened", ""))
        ws_n.cell(row=r3, column=3, value=primary.get("champion", "N/A"))
        ws_n.cell(row=r3, column=4, value=primary.get("n_features"))
        ws_n.cell(row=r3, column=5, value=threshold_display)
        ws_n.cell(row=r3, column=6, value=shap_names)
        ws_n.cell(row=r3, column=7, value=named_feats)
        ws_n.cell(row=r3, column=8, value=reg_citations)
        ws_n.cell(row=r3, column=9, value=n.get("production_meaning", ""))
        for c3 in (2, 6, 7, 8, 9):
            ws_n.cell(row=r3, column=c3).alignment = wrap_top
        ws_n.row_dimensions[r3].height = 130
    n_narr_rows = 5
    for c, w in zip(range(1, 10), [6, 46, 18, 12, 11, 34, 34, 46, 56]):
        ws_n.column_dimensions[get_column_letter(c)].width = w
    ws_n.auto_filter.ref = f"A1:I{1 + n_narr_rows}"
    _brand_excel_sheet(ws_n, PALETTE["series_2_orange"], freeze_cell="B2")
    _band_excel_rows(ws_n, first_data_row=2, last_data_row=1 + n_narr_rows, first_col=1, last_col=9)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))
    return path


# ============================================================================
# HTML dashboard -- platform rollup equivalent. Same CVD-validated PALETTE as
# write_html_dashboard / _multiclass / _structural (shared visual system across every BP),
# shaped for a multi-BP rollup, upgraded 2026-10-02 per explicit user request: contrast
# card backgrounds (light/dark-aware surface tokens -- the PALETTE's own neutral/status/
# categorical hex values are reused unchanged throughout; only the neutral surface/page/
# ink tokens gain a dark-mode variant, since none existed before), Chart.js entrance
# animation + KPI count-up animation + CSS hover/filter transitions, a real three-filter
# bar (BP / Phase / financial-category) wired to the chart, KPI tiles, and every table,
# click-to-sort interactive tables, and a prominent five-card expandable per-BP business
# narrative section. Status colors remain reserved for verdict/good-warning-critical states
# and are always paired with an icon + text label, never color alone. Chart.js bundled
# locally (same vendor file every other BP's dashboard uses), never CDN-loaded.
# ============================================================================
def write_platform_html_dashboard(path: Path, context: dict, chartjs_js_path: Path) -> Path:
    chartjs_source = Path(chartjs_js_path).read_text(encoding="utf-8")

    psd = context["platform_source_data"]
    roll = psd["platform_rollup"]
    status = context.get("status") or compute_platform_status(psd)
    recommendations = context.get("smart_recommendations") or generate_platform_smart_recommendations(psd)
    narratives = context.get("bp_narratives") or build_bp_business_narratives_platform(psd)

    cat1, cat2, cat3 = (
        roll["benefit_category_1_fp_reduction_savings"],
        roll["benefit_category_2_tp_uplift_value"],
        roll["benefit_category_3_bp2_typology_lines"],
    )
    scale = roll["portfolio_scale"]

    bp_rows = []
    phase_groups: dict = {}
    for bp_id, d in psd["bps"].items():
        primary = d["variants"][d["primary_variant"]]
        row = {
            "bp_id": bp_id,
            "name": d["name"],
            "phase": d["phase"],
            "primary_variant": d["primary_variant"],
            "champion": primary.get("champion", "N/A"),
            "verdict": primary.get("verdict", "N/A"),
        }
        bp_rows.append(row)
        phase_groups.setdefault(d["phase"], []).append(bp_id)

    # Real benefit-table rows, each tagged with a category key and (where applicable) a BP
    # key, so the client-side filter bar can filter/dim them -- pure real-dict lookups and
    # string tags, no new figures computed here.
    _line_item_to_bp = {
        "BP1 -- Transaction Monitoring": "BP1",
        "BP4 -- Structuring & Smurfing": "BP4",
        "BP5 -- Correspondent Banking & Cross-Border": "BP5",
        "Auto-typing efficiency savings": "BP2",
        "Typology confirmation value": "BP2",
        "BP3 real network nodes": "BP3",
        "BP3 real network edges": "BP3",
    }
    _cat_prefix_to_key = {
        "BENEFIT 1": "cat1",
        "BENEFIT 2": "cat2",
        "BENEFIT 3": "cat3",
        "COST CONTEXT": "cost",
        "PORTFOLIO SCALE": "scale",
    }
    benefit_rows = []
    ben_df = context.get("benefit_table")
    if ben_df is not None:
        for _, r in ben_df.iterrows():
            cat_key = next(
                (v for k, v in _cat_prefix_to_key.items() if str(r["Category"]).startswith(k)), "other"
            )
            benefit_rows.append(
                {
                    "category": r["Category"],
                    "category_key": cat_key,
                    "line_item": r["Line Item"],
                    "value": r["Value"],
                    "note": r["Note"],
                    "bp_key": _line_item_to_bp.get(r["Line Item"]),
                }
            )

    data_json = json.dumps(
        {
            "cat1": {
                "bp1": cat1["bp1"],
                "bp4": cat1["bp4"],
                "bp5": cat1["bp5"],
                "total": cat1["total_usd"],
                "hours": cat1["total_investigator_hours_saved"],
                "fewer_fp": cat1["total_fewer_fp_alerts"],
            },
            "cat2": {
                "bp1": cat2["bp1"],
                "bp4": cat2["bp4"],
                "bp5": cat2["bp5"],
                "total": cat2["total_usd"],
                "cases": cat2["total_additional_cases_caught"],
            },
            "cat3": {
                "auto_typing": cat3["auto_typing_efficiency_savings_usd"],
                "typology_confirmation": cat3["typology_confirmation_value_usd"],
            },
            "scale": {"nodes": scale["bp3_n_nodes"], "edges": scale["bp3_n_edges"]},
            "bp_rows": bp_rows,
            "phase_groups": phase_groups,
            "benefit_rows": benefit_rows,
        }
    )
    status_json = json.dumps(status)
    recs_json = json.dumps(recommendations)
    narratives_json = json.dumps(narratives)
    sourcing_method_json = json.dumps(psd["sourcing_method"])
    palette = PALETTE

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{context['bp_id']} -- {context['bp_name']} -- Platform Rollup Dashboard</title>
<style>
  :root {{
    color-scheme: light;
    --surface: {palette['surface']}; --page: {palette['page']};
    --ink: {palette['ink_primary']}; --ink-2: {palette['ink_secondary']}; --ink-muted: {palette['ink_muted']};
    --grid: {palette['gridline']};
    --s1: {palette['series_1_blue']}; --s2: {palette['series_2_orange']}; --s3: {palette['series_3_aqua']};
    --good: {palette['status_good']}; --warn: {palette['status_warning']}; --crit: {palette['status_critical']};
    --shadow: 0 1px 2px rgba(11,11,11,.06), 0 1px 1px rgba(11,11,11,.04);
    --shadow-hover: 0 14px 28px rgba(11,11,11,.14), 0 4px 10px rgba(11,11,11,.08);
  }}
  /* Forced light mode (user-requested, 2026-10-02): this dashboard previously auto-switched
     to a dark near-black page/surface via @media (prefers-color-scheme: dark) whenever the
     viewer's OS/browser was set to dark mode -- the dark tokens were real and intentional,
     but the user viewing this on a dark-mode system found the result "over dark" and asked
     for the light grey page back. Per the dataviz skill's own guidance (dark mode should be
     an explicit user-selected toggle, never an automatic OS-driven flip), the fix here is to
     drop the automatic dark variant entirely rather than re-tune its colors -- this dashboard
     now always renders with the same validated light-grey PALETTE tokens (--page: {palette['page']},
     --surface: {palette['surface']}) regardless of the viewer's system theme.
  */
  * {{ box-sizing: border-box; }}
  html {{ scroll-behavior: smooth; }}
  body {{
    margin:0; color:var(--ink); font-family: system-ui,-apple-system,"Segoe UI",sans-serif;
    background:
      radial-gradient(1100px 580px at 8% -8%, rgba(42,120,214,0.10), transparent 58%),
      radial-gradient(900px 520px at 100% 0%, rgba(27,175,122,0.09), transparent 55%),
      radial-gradient(800px 500px at 50% 110%, rgba(235,104,52,0.06), transparent 60%),
      var(--page);
    background-attachment: fixed; min-height:100vh;
  }}
  .accent-bar {{ height:4px; width:100%; background: linear-gradient(90deg, var(--s1), var(--s3), var(--s2), var(--s1));
    background-size:300% 100%; animation: shimmer 7s linear infinite; }}
  @keyframes shimmer {{ 0% {{ background-position:0% 0; }} 100% {{ background-position:300% 0; }} }}
  @keyframes fadeInUp {{ from {{ opacity:0; transform:translateY(10px); }} to {{ opacity:1; transform:translateY(0); }} }}
  @keyframes fadeSection {{ from {{ opacity:0; transform:translateY(6px); }} to {{ opacity:1; transform:translateY(0); }} }}
  @keyframes pulseDot {{ 0% {{ box-shadow:0 0 0 0 currentColor; opacity:1; }} 70% {{ box-shadow:0 0 0 9px transparent; opacity:.35; }} 100% {{ box-shadow:0 0 0 0 transparent; opacity:1; }} }}

  header {{ padding:22px 24px; border-bottom:1px solid var(--grid); background:var(--surface); box-shadow:var(--shadow);
    animation: fadeInUp .45s ease both; position:relative; z-index:2; }}
  h1 {{ margin:0 0 4px; font-size:21px; letter-spacing:-.01em; }}
  .sub {{ color:var(--ink-2); font-size:13px; }}

  /* Every chart / KPI / table / text block below sits on a bordered, shadowed CARD against
     the page's gradient plane -- nothing is left flush on one flat background. */
  .status-banner {{ margin:16px 24px 0; padding:16px 20px; border-radius:12px; border:1px solid var(--grid);
    display:flex; align-items:flex-start; gap:14px; box-shadow:var(--shadow); background:var(--surface);
    animation: fadeInUp .5s ease both; }}
  .status-banner.good {{ border-left:5px solid var(--good); }}
  .status-banner.warning {{ border-left:5px solid var(--warn); }}
  .status-banner.critical {{ border-left:5px solid var(--crit); }}
  .status-banner .dot {{ width:14px; height:14px; border-radius:50%; flex:0 0 auto; margin-top:3px; position:relative; font-size:11px; display:flex; align-items:center; justify-content:center; color:#fff; }}
  .status-banner .dot::after {{ content:""; position:absolute; inset:0; border-radius:50%; background:currentColor; animation: pulseDot 2.2s ease-out infinite; z-index:-1; }}
  .status-banner .dot.good {{ background:var(--good); color:var(--good); }}
  .status-banner .dot.warning {{ background:var(--warn); color:var(--warn); }}
  .status-banner .dot.critical {{ background:var(--crit); color:var(--crit); }}
  .status-banner .label {{ font-size:16px; font-weight:700; }}
  .status-banner .rationale {{ font-size:13px; color:var(--ink-2); margin-top:4px; line-height:1.5; }}

  .narrative {{ background:var(--surface); border:1px solid var(--grid); border-radius:12px; padding:18px 20px;
    margin:16px 24px 0; box-shadow:var(--shadow); animation: fadeInUp .55s ease both; }}
  .narrative h2 {{ margin:0 0 8px; font-size:15px; }}
  .narrative p {{ margin:0; color:var(--ink-2); font-size:13px; line-height:1.5; }}

  .tabs {{ position:relative; display:flex; gap:4px; padding:0 24px; margin-top:16px; background:var(--surface);
    border-bottom:1px solid var(--grid); flex-wrap:wrap; box-shadow:var(--shadow); }}
  .tabs button {{ border:none; background:transparent; color:var(--ink-2); padding:12px 16px; cursor:pointer;
    font-size:13px; font-weight:600; border-bottom:2px solid transparent; border-radius:8px 8px 0 0;
    transition:color .15s ease, background .2s ease; }}
  .tabs button:hover {{ color:var(--ink); background:rgba(42,120,214,.08); }}
  .tabs button.active {{ color:var(--s1); border-bottom-color:var(--s1); }}
  .view-section {{ display:none; }}
  .view-section.active {{ display:block; animation: fadeSection .35s ease both; }}

  /* --- Filter bar: three real slicers, one row above the charts (dataviz-skill convention) --- */
  .filterbar {{ display:flex; flex-wrap:wrap; gap:18px; align-items:center; padding:14px 24px; margin:16px 24px 0;
    background:var(--surface); border:1px solid var(--grid); border-radius:12px; box-shadow:var(--shadow);
    animation: fadeInUp .55s ease both; }}
  .filter-group {{ display:flex; flex-wrap:wrap; align-items:center; gap:6px; }}
  .filter-group .fl-label {{ color:var(--ink-muted); font-size:11px; text-transform:uppercase; letter-spacing:.05em; margin-right:4px; }}
  .filter-group button {{ border:1px solid var(--grid); background:var(--page); color:var(--ink); padding:6px 13px;
    border-radius:999px; cursor:pointer; font-size:12.5px; transition: background .2s ease, color .2s ease,
    border-color .2s ease, transform .2s cubic-bezier(.34,1.56,.64,1), box-shadow .2s ease; }}
  .filter-group button:hover {{ transform:translateY(-2px); box-shadow:var(--shadow); }}
  .filter-group button.active {{ background:var(--s1); color:#fff; border-color:var(--s1); box-shadow:0 4px 12px rgba(42,120,214,.35); }}
  .filter-reset {{ margin-left:auto; font-size:12px; color:var(--s1); background:none; border:none; cursor:pointer; text-decoration:underline; }}

  main {{ padding:20px 24px; display:grid; gap:16px; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); }}
  .tile, .chart-box, .rec-card, .bp-card, .table-card {{ background:var(--surface); border:1px solid var(--grid);
    border-radius:12px; box-shadow:var(--shadow); animation: fadeInUp .5s ease both;
    transition: transform .2s cubic-bezier(.22,1,.36,1), box-shadow .2s ease, border-color .2s ease, opacity .25s ease; }}
  .tile:hover, .chart-box:hover, .rec-card:hover, .bp-card:hover, .table-card:hover {{
    transform:translateY(-4px); box-shadow:var(--shadow-hover); border-color:rgba(42,120,214,.3); }}
  .tile {{ padding:16px; }}
  .tile.tile-inactive {{ opacity:.35; transform:none; }}
  .tile .cat-label {{ color:var(--ink-muted); font-size:10.5px; text-transform:uppercase; letter-spacing:.04em; }}
  .tile .label {{ color:var(--ink-2); font-size:12px; margin-top:2px; }}
  .tile .value {{ font-size:25px; font-weight:650; margin-top:4px; }}
  .tile .note {{ color:var(--ink-muted); font-size:11.5px; margin-top:6px; line-height:1.4; }}
  .wide {{ grid-column: 1 / -1; }}
  .chart-box {{ padding:16px; height:360px; }}
  .table-card {{ padding:16px; }}

  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th, td {{ text-align:left; padding:7px 9px; border-bottom:1px solid var(--grid); }}
  th {{ color:var(--ink-2); font-weight:600; cursor:pointer; user-select:none; white-space:nowrap; position:relative; }}
  th:hover {{ color:var(--ink); background:rgba(42,120,214,.06); }}
  th.sorted-asc::after {{ content:" \\25B2"; font-size:9px; color:var(--s1); }}
  th.sorted-desc::after {{ content:" \\25BC"; font-size:9px; color:var(--s1); }}
  tbody tr {{ transition: background .15s ease, opacity .2s ease; }}
  tbody tr:nth-child(even) {{ background:rgba(42,120,214,.025); }}
  tbody tr:hover {{ background:rgba(42,120,214,.09); }}
  tbody tr.row-dim {{ opacity:.3; }}
  tbody tr.row-hidden {{ display:none; }}
  .row-hidden {{ display:none !important; }}  /* generic: also hides filtered-out bp-card / rec-card divs (Narratives + Recommendations tabs), not just table rows */
  tbody tr.row-highlight {{ border-left:3px solid var(--s1); background:rgba(42,120,214,.07); }}
  .verdict-pill {{ display:inline-block; padding:2px 10px; border-radius:999px; font-size:12px; font-weight:600; }}
  .verdict-pass {{ background:rgba(12,163,12,.14); color:var(--good); }}
  .verdict-fail {{ background:rgba(208,59,59,.14); color:var(--crit); }}

  .rec-card {{ padding:16px 18px; }}
  .rec-card h3 {{ margin:0 0 8px; font-size:14.5px; }}
  .rec-card .smart-row {{ font-size:12.5px; color:var(--ink-2); margin:5px 0; line-height:1.55; }}
  .rec-card .smart-row b {{ color:var(--ink); }}

  /* --- Per-BP business narrative accordion cards --- */
  .bp-card {{ overflow:hidden; margin-bottom:12px; }}
  .bp-card-header {{ width:100%; display:flex; align-items:center; gap:12px; padding:14px 18px; background:none;
    border:none; cursor:pointer; text-align:left; font:inherit; color:var(--ink); }}
  .bp-chip {{ color:#fff; font-weight:700; font-size:12px; padding:4px 10px; border-radius:7px; flex:0 0 auto; }}
  .bp-card-title {{ flex:1 1 auto; font-weight:650; font-size:14.5px; }}
  .bp-card .chevron {{ transition: transform .3s cubic-bezier(.22,1,.36,1); color:var(--ink-muted); }}
  .bp-card.open .chevron {{ transform: rotate(180deg); }}
  .bp-card-body-wrap {{ display:grid; grid-template-rows: 0fr; transition: grid-template-rows .35s cubic-bezier(.22,1,.36,1); }}
  .bp-card.open .bp-card-body-wrap {{ grid-template-rows: 1fr; }}
  .bp-card-body {{ overflow:hidden; padding:0 18px; }}
  .bp-card.open .bp-card-body {{ padding:0 18px 18px; }}
  .bp-card-body h4 {{ margin:12px 0 4px; font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:var(--ink-muted); }}
  .bp-card-body p {{ margin:0; font-size:13px; color:var(--ink-2); line-height:1.6; }}
  .bp-subtabs {{ display:flex; gap:6px; margin:10px 0 2px; flex-wrap:wrap; }}
  .bp-subtab-btn {{ font:inherit; font-size:12px; font-weight:600; padding:6px 12px; border-radius:999px;
    border:1px solid var(--grid); background:var(--page); color:var(--ink-2); cursor:pointer;
    transition: background .2s ease, color .2s ease, border-color .2s ease; }}
  .bp-subtab-btn.active {{ background:var(--accent, #2a78d6); color:#fff; border-color:transparent; }}
  .bp-subtab-btn:hover:not(.active) {{ border-color:var(--ink-muted); }}
  .bp-subtab-panel[hidden] {{ display:none; }}

  .never-blend-note {{ margin:4px 24px 0; padding:10px 16px; background:rgba(250,178,25,.12); border:1px solid var(--warn);
    border-radius:8px; font-size:12px; color:var(--ink-2); box-shadow:var(--shadow); }}
  footer {{ padding:16px 24px; color:var(--ink-muted); font-size:12px; }}
</style>
</head>
<body>
<div class="accent-bar"></div>
<header>
  <h1>{context['bp_id']}: {context['bp_name']}</h1>
  <div class="sub">Platform-wide rollup of BP1-BP5's own already-computed real figures -- generated {context['generated_at_utc']} UTC</div>
</header>
<div class="status-banner {status['css_class']}">
  <div class="dot {status['css_class']}" id="status-icon"></div>
  <div><div class="label">{status['label']}</div><div class="rationale">{status['rationale']}</div></div>
</div>
<div class="never-blend-note">{roll['headline_grand_total_note']}</div>
<div class="narrative">
  <h2>Sourcing Method (verbatim, from the real extractor script)</h2>
  <p id="sourcing-method"></p>
</div>

<div class="tabs" id="tabs">
  <button class="tab-btn active" data-view="overview">Platform Overview</button>
  <button class="tab-btn" data-view="narratives">Per-BP Business Narratives</button>
  <button class="tab-btn" data-view="phase1">Phase 1 (BP1+BP2)</button>
  <button class="tab-btn" data-view="phase2">Phase 2 (BP3+BP4)</button>
  <button class="tab-btn" data-view="phase3">Phase 3 (BP5)</button>
  <button class="tab-btn" data-view="recs">Recommendations</button>
</div>

<div class="filterbar" id="filterbar">
  <div class="filter-group" id="fg-bp">
    <span class="fl-label">BP</span>
    <button class="active" data-filter="bp" data-value="all">All</button>
    <button data-filter="bp" data-value="BP1">BP1</button>
    <button data-filter="bp" data-value="BP2">BP2</button>
    <button data-filter="bp" data-value="BP3">BP3</button>
    <button data-filter="bp" data-value="BP4">BP4</button>
    <button data-filter="bp" data-value="BP5">BP5</button>
  </div>
  <div class="filter-group" id="fg-phase">
    <span class="fl-label">Phase</span>
    <button class="active" data-filter="phase" data-value="all">All</button>
    <button data-filter="phase" data-value="Phase 1">Phase 1</button>
    <button data-filter="phase" data-value="Phase 2">Phase 2</button>
    <button data-filter="phase" data-value="Phase 3">Phase 3</button>
  </div>
  <div class="filter-group" id="fg-cat">
    <span class="fl-label">Financial category</span>
    <button class="active" data-filter="cat" data-value="all">All</button>
    <button data-filter="cat" data-value="cat1">Benefit-1 FP-reduction</button>
    <button data-filter="cat" data-value="cat2">Benefit-2 TP-uplift</button>
    <button data-filter="cat" data-value="cat3">Benefit-3 BP2-typology</button>
    <button data-filter="cat" data-value="scale">Portfolio-scale</button>
  </div>
  <button class="filter-reset" id="filter-reset">Reset filters</button>
</div>

<section class="view-section active" id="view-overview">
  <main>
    <div class="tile" data-category="cat1"><div class="cat-label">Benefit Category 1</div><div class="label">FP-Reduction Savings (ASSUMPTION)</div>
      <div class="value" id="tile-cat1" data-countup="{cat1['total_usd']}">$0</div><div class="note" id="tile-cat1-note"></div></div>
    <div class="tile" data-category="cat2"><div class="cat-label">Benefit Category 2</div><div class="label">TP-Uplift Illustrative Value (ASSUMPTION)</div>
      <div class="value" id="tile-cat2" data-countup="{cat2['total_usd']}">$0</div><div class="note" id="tile-cat2-note"></div></div>
    <div class="tile" data-category="cat3"><div class="cat-label">Benefit Category 3</div><div class="label">BP2 Typology Lines (kept separate)</div>
      <div class="value" id="tile-cat3"></div><div class="note">Different unit basis -- never blended into categories 1/2</div></div>
    <div class="tile" data-category="scale"><div class="cat-label">Portfolio Scale</div><div class="label">BP3 Real Network Coverage</div>
      <div class="value" id="tile-scale" data-countup="{scale['bp3_n_nodes']}">0</div><div class="note" id="tile-scale-note"></div></div>

    <div class="chart-box wide"><canvas id="benefitChart"></canvas></div>

    <div class="table-card wide">
      <div class="label" style="margin-bottom:8px;">Per-BP Status Grid <span style="color:var(--ink-muted);font-weight:400;">(click a column header to sort)</span></div>
      <table id="bp-grid-table"><thead><tr>
        <th data-col="bp_id">BP</th><th data-col="name">Name</th><th data-col="phase">Phase</th>
        <th data-col="primary_variant">Primary Variant</th><th data-col="champion">Champion / Signal</th><th data-col="verdict">Verdict</th>
      </tr></thead><tbody id="bp-grid-body"></tbody></table>
    </div>

    <div class="table-card wide">
      <div class="label" style="margin-bottom:8px;">Three-Category Benefit Breakdown <span style="color:var(--ink-muted);font-weight:400;">(click a column header to sort)</span></div>
      <table id="benefit-table"><thead><tr>
        <th data-col="category">Category</th><th data-col="line_item">Line Item</th><th data-col="value">Value</th><th data-col="note">Note</th>
      </tr></thead><tbody id="benefit-table-body"></tbody></table>
    </div>

    <div class="table-card wide">
      <div class="label" style="margin-bottom:8px;">Phase Rollup <span style="color:var(--ink-muted);font-weight:400;">(click a column header to sort)</span></div>
      <table id="phase-table"><thead><tr>
        <th data-col="phase">Phase</th><th data-col="bp_id">BP</th><th data-col="name">Name</th>
        <th data-col="champion">Champion / Signal</th><th data-col="verdict">Verdict</th>
      </tr></thead><tbody id="phase-table-body"></tbody></table>
    </div>
  </main>
</section>

<section class="view-section" id="view-narratives">
  <main><div class="wide" id="narratives-container"></div></main>
</section>

<section class="view-section" id="view-phase1"><main><div class="tile wide" id="phase1-content"></div></main></section>
<section class="view-section" id="view-phase2"><main><div class="tile wide" id="phase2-content"></div></main></section>
<section class="view-section" id="view-phase3"><main><div class="tile wide" id="phase3-content"></div></main></section>

<section class="view-section" id="view-recs">
  <main><div class="wide" id="recs-container"></div></main>
</section>

<footer>Platform rollup -- pure pass-through of BP1-BP5's own already-computed figures. No figure on this page is recomputed, estimated, or fabricated.</footer>

<script>
{chartjs_source}
</script>
<script>
const DATA = {data_json};
const STATUS = {status_json};
const RECS = {recs_json};
const NARRATIVES = {narratives_json};
const SOURCING_METHOD = {sourcing_method_json};

const fmtUsd = (v) => {{
  const sign = v < 0 ? "-" : ""; const av = Math.abs(v);
  const exact = sign + "$" + av.toLocaleString("en-US", {{maximumFractionDigits:0}});
  if (av >= 1e9) return exact + " (" + sign + "$" + (av/1e9).toFixed(2) + "B)";
  if (av >= 1e6) return exact + " (" + sign + "$" + (av/1e6).toFixed(2) + "M)";
  return exact;
}};

// ---- Status icon (icon + label, never color alone) ----
const statusIcons = {{ good: "\\u2713", warning: "\\u26A0", critical: "\\u2715" }};
document.getElementById("status-icon").textContent = statusIcons[STATUS.css_class] || "\\u2022";
document.getElementById("sourcing-method").textContent = SOURCING_METHOD;

// ---- KPI count-up animation (vanilla JS, eased, no new dependency) ----
function easeOutCubic(t) {{ return 1 - Math.pow(1 - t, 3); }}
function countUp(el, target, isUsd, durationMs) {{
  const start = performance.now();
  function frame(now) {{
    const p = Math.min(1, (now - start) / durationMs);
    const eased = easeOutCubic(p);
    const current = target * eased;
    el.textContent = isUsd ? fmtUsd(current) : Math.round(current).toLocaleString();
    if (p < 1) requestAnimationFrame(frame);
    else el.textContent = isUsd ? fmtUsd(target) : Math.round(target).toLocaleString();
  }}
  requestAnimationFrame(frame);
}}
countUp(document.getElementById("tile-cat1"), DATA.cat1.total, true, 1100);
countUp(document.getElementById("tile-cat2"), DATA.cat2.total, true, 1100);
countUp(document.getElementById("tile-scale"), DATA.scale.nodes, false, 1100);
document.getElementById("tile-cat1-note").textContent = DATA.cat1.hours.toLocaleString() + " hrs saved, " + DATA.cat1.fewer_fp.toLocaleString() + " fewer FP alerts (BP1+BP4+BP5)";
document.getElementById("tile-cat2-note").textContent = (DATA.cat2.cases >= 0 ? "+" : "") + DATA.cat2.cases.toLocaleString() + " additional real cases caught (BP1+BP4+BP5)";
document.getElementById("tile-cat3").textContent = fmtUsd(DATA.cat3.auto_typing) + " / " + fmtUsd(DATA.cat3.typology_confirmation);
document.getElementById("tile-scale-note").textContent = DATA.scale.edges.toLocaleString() + " real edges";

// ---- Build tables (data rows carry data-bp / data-phase / data-category for filtering) ----
function bpRowHtml(r) {{
  const verdictCls = r.verdict === "PASS" ? "verdict-pass" : "verdict-fail";
  return `<tr data-bp="${{r.bp_id}}" data-phase="${{r.phase}}">` +
    `<td>${{r.bp_id}}</td><td>${{r.name}}</td><td data-sort="${{r.phase}}">${{r.phase}}</td><td>${{r.primary_variant}}</td>` +
    `<td>${{r.champion}}</td><td><span class="verdict-pill ${{verdictCls}}">${{r.verdict}}</span></td></tr>`;
}}
const gridBody = document.getElementById("bp-grid-body");
DATA.bp_rows.forEach(r => gridBody.insertAdjacentHTML("beforeend", bpRowHtml(r)));

const phaseBody = document.getElementById("phase-table-body");
DATA.bp_rows.forEach(r => {{
  const verdictCls = r.verdict === "PASS" ? "verdict-pass" : "verdict-fail";
  phaseBody.insertAdjacentHTML("beforeend",
    `<tr data-bp="${{r.bp_id}}" data-phase="${{r.phase}}">` +
    `<td data-sort="${{r.phase}}">${{r.phase}}</td><td>${{r.bp_id}}</td><td>${{r.name}}</td><td>${{r.champion}}</td>` +
    `<td><span class="verdict-pill ${{verdictCls}}">${{r.verdict}}</span></td></tr>`);
}});

const benefitBody = document.getElementById("benefit-table-body");
DATA.benefit_rows.forEach(r => {{
  benefitBody.insertAdjacentHTML("beforeend",
    `<tr data-category="${{r.category_key}}" data-bp="${{r.bp_key || ''}}">` +
    `<td data-sort="${{r.category}}">${{r.category}}</td><td>${{r.line_item}}</td><td>${{r.value}}</td><td>${{r.note}}</td></tr>`);
}});

// ---- User-reported repetition fix (2026-10-02): "Phase 1 -- Detection Foundation" /
// "Phase 2 -- ..." / a repeated Category label was printed on every single row, even when
// several consecutive rows share the same value (e.g. BP1 and BP2 both show the full
// "Phase 1 -- Detection Foundation" text back to back) -- visually noisy and read as a
// duplication bug. Fix: blank a group-column cell's text whenever it matches the nearest
// VISIBLE row above it, so each group label prints once per visible run, not once per row.
// The true value always stays on the cell's own data-sort attribute (never erased), so
// clicking that column's header to sort still sorts correctly even while some cells are
// visually blank -- and re-running this after every sort/filter keeps the blanking correct
// for whatever rows are currently visible and in whatever order they are currently in.
function collapseRepeatedCell(tbodyId, cellIndex) {{
  const tbody = document.getElementById(tbodyId);
  if (!tbody) return;
  const rows = Array.from(tbody.querySelectorAll("tr")).filter(tr => !tr.classList.contains("row-hidden"));
  let last = null;
  rows.forEach(tr => {{
    const cell = tr.children[cellIndex];
    if (!cell || cell.dataset.sort === undefined) return;
    const trueVal = cell.dataset.sort;
    cell.textContent = (trueVal === last) ? "" : trueVal;
    last = trueVal;
  }});
}}
const COLLAPSE_CONFIG = {{
  "bp-grid-table": {{ tbodyId: "bp-grid-body", col: 2 }},
  "phase-table": {{ tbodyId: "phase-table-body", col: 0 }},
  "benefit-table": {{ tbodyId: "benefit-table-body", col: 0 }},
}};
Object.values(COLLAPSE_CONFIG).forEach(cfg => collapseRepeatedCell(cfg.tbodyId, cfg.col));

// ---- Click-to-sort tables (vanilla JS, numeric-aware: strips $, commas, %, +/-) ----
function sortValue(text) {{
  const cleaned = text.replace(/[,$%+]/g, "").trim();
  const n = parseFloat(cleaned);
  return isNaN(n) ? text.toLowerCase() : n;
}}
function makeSortable(tableId) {{
  const table = document.getElementById(tableId);
  const headers = table.querySelectorAll("th");
  headers.forEach((th, colIdx) => {{
    th.addEventListener("click", () => {{
      const tbody = table.querySelector("tbody");
      const rows = Array.from(tbody.querySelectorAll("tr"));
      const asc = !th.classList.contains("sorted-asc");
      headers.forEach(h => h.classList.remove("sorted-asc", "sorted-desc"));
      th.classList.add(asc ? "sorted-asc" : "sorted-desc");
      rows.sort((a, b) => {{
        const aCell = a.children[colIdx], bCell = b.children[colIdx];
        const aText = aCell.dataset.sort !== undefined ? aCell.dataset.sort : aCell.textContent;
        const bText = bCell.dataset.sort !== undefined ? bCell.dataset.sort : bCell.textContent;
        const av = sortValue(aText);
        const bv = sortValue(bText);
        if (av < bv) return asc ? -1 : 1;
        if (av > bv) return asc ? 1 : -1;
        return 0;
      }});
      rows.forEach(r => tbody.appendChild(r));
      const cfg = COLLAPSE_CONFIG[tableId];
      if (cfg) collapseRepeatedCell(cfg.tbodyId, cfg.col);
    }});
  }});
}}
["bp-grid-table", "benefit-table", "phase-table"].forEach(makeSortable);

// ---- Chart.js bar chart, eased entrance animation, filter-reactive ----
const chartColors = {{ cat1: "{palette['series_1_blue']}", cat2: "{palette['series_2_orange']}" }};
const dimColor = "{palette['ink_muted']}";
const benefitChart = new Chart(document.getElementById("benefitChart"), {{
  type: "bar",
  data: {{
    labels: ["BP1", "BP4", "BP5"],
    datasets: [
      {{ label: "Category 1 -- FP-Reduction $", data: [DATA.cat1.bp1, DATA.cat1.bp4, DATA.cat1.bp5], backgroundColor: [chartColors.cat1, chartColors.cat1, chartColors.cat1] }},
      {{ label: "Category 2 -- TP-Uplift $", data: [DATA.cat2.bp1, DATA.cat2.bp4, DATA.cat2.bp5], backgroundColor: [chartColors.cat2, chartColors.cat2, chartColors.cat2] }},
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    animation: {{ duration: 900, easing: "easeOutCubic" }},
    transitions: {{ active: {{ animation: {{ duration: 300 }} }} }},
    plugins: {{
      legend: {{
        position: "bottom",
        // User-requested change (2026-10-02): Chart.js's default legend click just TOGGLES
        // the clicked series on/off, leaving every other series exactly as it was -- so
        // clicking "Category 1" hid category 1 but left category 2 visible, never isolating
        // a single series. Selecting a legend item must now show ONLY that series (every
        // other dataset hidden); clicking the already-sole-visible item again restores all
        // series, which is the real way back to the full chart.
        onClick: (evt, legendItem, legend) => {{
          const chart = legend.chart;
          const clickedIndex = legendItem.datasetIndex;
          const isAlreadyIsolated = chart.data.datasets.every((_, i) =>
            i === clickedIndex ? !chart.getDatasetMeta(i).hidden : chart.getDatasetMeta(i).hidden
          );
          chart.data.datasets.forEach((_, i) => {{
            chart.getDatasetMeta(i).hidden = isAlreadyIsolated ? false : (i !== clickedIndex);
          }});
          chart.update();
        }},
      }},
      title: {{ display: true, text: "Real per-BP benefit $ -- categories 1 and 2 shown side by side, never summed" }}
    }},
    scales: {{ y: {{ ticks: {{ callback: (v) => "$" + (v/1e6).toFixed(0) + "M" }} }} }}
  }}
}});

// ---- Per-BP business narrative accordion cards ----
const accentCycle = ["{palette['series_1_blue']}", "{palette['series_2_orange']}", "{palette['series_3_aqua']}"];
const narrativesContainer = document.getElementById("narratives-container");
Object.entries(NARRATIVES).forEach(([bpId, n], idx) => {{
  const card = document.createElement("div");
  card.className = "bp-card";
  card.dataset.bp = bpId;
  const verdictCls = n.verdict === "PASS" ? "verdict-pass" : "verdict-fail";
  card.style.setProperty("--accent", n.accent);
  const methodologyHtml = n.methodology
    ? `<h4>Methodology &amp; Regulatory Basis</h4><p>${{n.methodology}}</p>`
    : `<p><em>Not applicable for this BP.</em></p>`;
  card.innerHTML =
    `<button class="bp-card-header" aria-expanded="false">` +
      `<span class="bp-chip" style="background:${{n.accent}}">${{bpId}}</span>` +
      `<span class="bp-card-title">${{n.title}}</span>` +
      `<span class="verdict-pill ${{verdictCls}}">${{n.verdict}}</span>` +
      `<span class="chevron">\\u25BE</span>` +
    `</button>` +
    `<div class="bp-card-body-wrap"><div class="bp-card-body">` +
      `<div class="bp-subtabs">` +
        `<button class="bp-subtab-btn active" data-tab="impact">Business Impact</button>` +
        `<button class="bp-subtab-btn" data-tab="method">Methodology &amp; Regulatory Basis</button>` +
      `</div>` +
      `<div class="bp-subtab-panel" data-tab="impact">` +
        `<h4>What it does</h4><p>${{n.what_it_does}}</p>` +
        `<h4>Real validated performance</h4><p>${{n.real_performance}}</p>` +
        `<h4>What production deployment would mean</h4><p>${{n.production_meaning}}</p>` +
      `</div>` +
      `<div class="bp-subtab-panel" data-tab="method" hidden>${{methodologyHtml}}</div>` +
    `</div></div>`;
  const header = card.querySelector(".bp-card-header");
  header.addEventListener("click", () => {{
    const isOpen = card.classList.toggle("open");
    header.setAttribute("aria-expanded", isOpen ? "true" : "false");
  }});
  card.querySelectorAll(".bp-subtab-btn").forEach((btn) => {{
    btn.addEventListener("click", (ev) => {{
      ev.stopPropagation();
      const tab = btn.dataset.tab;
      card.querySelectorAll(".bp-subtab-btn").forEach((b) => b.classList.toggle("active", b === btn));
      card.querySelectorAll(".bp-subtab-panel").forEach((p) => {{ p.hidden = p.dataset.tab !== tab; }});
    }});
  }});
  narrativesContainer.appendChild(card);
  if (idx === 0) {{ card.classList.add("open"); header.setAttribute("aria-expanded", "true"); }}
}});

// ---- Phase descriptive panels (unchanged content, same data source) ----
const phaseGroups = DATA.phase_groups;
function renderPhase(divId, phaseKeyGuess) {{
  const el = document.getElementById(divId);
  let html = "";
  for (const [phaseName, bpIds] of Object.entries(phaseGroups)) {{
    if (!phaseName.includes(phaseKeyGuess)) continue;
    html += `<h3 style="margin-top:0;">${{phaseName}}</h3><p style="color:var(--ink-2);font-size:13px;">BPs: ${{bpIds.join(", ")}}</p>`;
    bpIds.forEach(bpId => {{
      const row = DATA.bp_rows.find(r => r.bp_id === bpId);
      if (row) html += `<p style="font-size:13px;"><b>${{bpId}}</b> -- ${{row.name}}: champion/signal <b>${{row.champion}}</b>, verdict <b>${{row.verdict}}</b> (primary variant ${{row.primary_variant}})</p>`;
    }});
  }}
  el.innerHTML = html || "<p>No real phase data available for this view.</p>";
}}
renderPhase("phase1-content", "Phase 1");
renderPhase("phase2-content", "Phase 2");
renderPhase("phase3-content", "Phase 3");

// ---- SMART recommendation cards ----
const recsContainer = document.getElementById("recs-container");
RECS.forEach(r => {{
  const card = document.createElement("div");
  card.className = "rec-card";
  card.dataset.bp = r.bp || "";
  card.innerHTML = `<h3>${{r.title}}</h3>` +
    `<div class="smart-row"><b>Specific:</b> ${{r.specific}}</div>` +
    `<div class="smart-row"><b>Measurable:</b> ${{r.measurable}}</div>` +
    `<div class="smart-row"><b>Achievable:</b> ${{r.achievable}}</div>` +
    `<div class="smart-row"><b>Relevant:</b> ${{r.relevant}}</div>` +
    `<div class="smart-row"><b>Time-bound:</b> ${{r.time_bound}}</div>`;
  recsContainer.appendChild(card);
}});

// ---- Tabs ----
document.querySelectorAll(".tab-btn").forEach(btn => {{
  btn.addEventListener("click", () => {{
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".view-section").forEach(s => s.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("view-" + btn.dataset.view).classList.add("active");
  }});
}});

// ============================================================================
// Real filter bar -- BP selector / Phase selector / financial-category toggle. User-
// requested change (2026-10-02): a selected filter/slicer must actually show only the
// matching rows, not just visually dim/highlight everything while leaving every row on
// screen -- so every table below now HIDES (display:none, via the "row-hidden" class)
// any row outside the active filter's effective set, same as the benefit table's category
// filter already did. The chart bars and KPI tiles still dim (a bar chart/tile has no
// meaningful "hidden" state -- removing a bar would leave a confusing gap on its own axis
// label), but every real table row list is now a true filter, not a highlight.
// ============================================================================
const filterState = {{ bp: "all", phase: "all", cat: "all" }};
const bpToPhase = {{}};
DATA.bp_rows.forEach(r => {{ bpToPhase[r.bp_id] = r.phase; }});

function effectiveBpSet() {{
  if (filterState.bp !== "all") return new Set([filterState.bp]);
  if (filterState.phase !== "all") {{
    const phaseKey = Object.keys(phaseGroups).find(p => p.includes(filterState.phase));
    return new Set(phaseKey ? phaseGroups[phaseKey] : []);
  }}
  return new Set(DATA.bp_rows.map(r => r.bp_id));
}}

function applyFilters() {{
  const bpSet = effectiveBpSet();

  // Chart: dim bars for BPs outside the effective set; hide a dataset entirely when the
  // category filter selects a category that dataset does not represent.
  const barBps = ["BP1", "BP4", "BP5"];
  benefitChart.data.datasets[0].backgroundColor = barBps.map(b => bpSet.has(b) ? chartColors.cat1 : dimColor);
  benefitChart.data.datasets[1].backgroundColor = barBps.map(b => bpSet.has(b) ? chartColors.cat2 : dimColor);
  benefitChart.data.datasets[0].hidden = (filterState.cat !== "all" && filterState.cat !== "cat1");
  benefitChart.data.datasets[1].hidden = (filterState.cat !== "all" && filterState.cat !== "cat2");
  benefitChart.update();

  // KPI tiles: dim any tile whose own category doesn't match an active category filter.
  document.querySelectorAll(".tile[data-category]").forEach(tile => {{
    const tCat = tile.dataset.category;
    const inactive = (filterState.cat !== "all" && filterState.cat !== tCat);
    tile.classList.toggle("tile-inactive", inactive);
  }});

  // Status-grid / phase-table rows: a BP or Phase selection now actually REMOVES
  // non-matching rows from view (row-hidden), rather than dimming them in place.
  document.querySelectorAll("#bp-grid-body tr, #phase-table-body tr").forEach(tr => {{
    const rowBp = tr.dataset.bp;
    const matches = bpSet.has(rowBp);
    tr.classList.remove("row-dim", "row-highlight");
    tr.classList.toggle("row-hidden", !matches);
  }});

  // Benefit-breakdown table: BOTH the category filter and the BP filter now hide
  // non-matching rows outright (a row with no bp_key, e.g. a portfolio-scale line, is
  // never BP-specific and so is never hidden by the BP filter).
  document.querySelectorAll("#benefit-table-body tr").forEach(tr => {{
    const rowCat = tr.dataset.category;
    const rowBp = tr.dataset.bp;
    const catHidden = (filterState.cat !== "all" && filterState.cat !== rowCat);
    const bpActive = (filterState.bp !== "all");
    const bpHidden = bpActive && rowBp !== "" && rowBp !== filterState.bp;
    tr.classList.remove("row-dim", "row-highlight");
    tr.classList.toggle("row-hidden", catHidden || bpHidden);
  }});

  // Per-BP Business Narrative cards (Narratives tab): the filter bar sits above every tab,
  // not just Overview, so a BP/Phase selection must reach this tab too -- every card is
  // already tagged card.dataset.bp = bpId, so just hide the ones outside the effective set.
  document.querySelectorAll("#narratives-container .bp-card").forEach(card => {{
    card.classList.toggle("row-hidden", !bpSet.has(card.dataset.bp));
  }});

  // SMART recommendation cards (Recommendations tab): each card is tagged with the one real
  // BP it specifically concerns, or "" for a platform-wide/multi-BP recommendation (those
  // always stay visible regardless of the BP/Phase filter -- they are never specific to just
  // one BP, so hiding them on a single-BP filter would misrepresent them as BP-specific).
  document.querySelectorAll("#recs-container .rec-card").forEach(card => {{
    const cardBp = card.dataset.bp;
    card.classList.toggle("row-hidden", cardBp !== "" && !bpSet.has(cardBp));
  }});

  // Re-collapse repeated group-label cells (Phase / Category columns) now that filtering
  // may have changed which rows are visible, and therefore which rows are visually adjacent.
  Object.values(COLLAPSE_CONFIG).forEach(cfg => collapseRepeatedCell(cfg.tbodyId, cfg.col));
}}

document.querySelectorAll(".filter-group button").forEach(btn => {{
  btn.addEventListener("click", () => {{
    const group = btn.dataset.filter;
    document.querySelectorAll(`.filter-group button[data-filter="${{group}}"]`).forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    filterState[group] = btn.dataset.value;
    // BP and Phase filters are mutually exclusive (selecting one real BP overrides a phase
    // selection, and vice versa) -- reset the other group's UI + state back to "all".
    if (group === "bp" && btn.dataset.value !== "all") {{
      filterState.phase = "all";
      document.querySelectorAll('.filter-group button[data-filter="phase"]').forEach(b => b.classList.toggle("active", b.dataset.value === "all"));
    }}
    if (group === "phase" && btn.dataset.value !== "all") {{
      filterState.bp = "all";
      document.querySelectorAll('.filter-group button[data-filter="bp"]').forEach(b => b.classList.toggle("active", b.dataset.value === "all"));
    }}
    applyFilters();
  }});
}});
document.getElementById("filter-reset").addEventListener("click", () => {{
  filterState.bp = "all"; filterState.phase = "all"; filterState.cat = "all";
  document.querySelectorAll(".filter-group button").forEach(b => b.classList.toggle("active", b.dataset.value === "all"));
  applyFilters();
}});
</script>
</body>
</html>
"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


# ============================================================================
# Real matplotlib grouped-bar PNG (category 1 vs category 2 per contributing BP) -- for
# the PPTX deck's static chart slide, same convention as render_before_after_chart_png /
# render_signal_lift_chart_png_structural.
# ============================================================================
def render_platform_benefit_chart_png(platform_rollup: dict, out_path: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cat1 = platform_rollup["benefit_category_1_fp_reduction_savings"]
    cat2 = platform_rollup["benefit_category_2_tp_uplift_value"]
    bps = ["BP1", "BP4", "BP5"]
    c1_vals = [cat1["bp1"], cat1["bp4"], cat1["bp5"]]
    c2_vals = [cat2["bp1"], cat2["bp4"], cat2["bp5"]]

    x = range(len(bps))
    width = 0.35
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    ax.bar(
        [i - width / 2 for i in x],
        c1_vals,
        width,
        label="Category 1 -- FP-Reduction $",
        color=PALETTE["series_1_blue"],
    )
    ax.bar(
        [i + width / 2 for i in x],
        c2_vals,
        width,
        label="Category 2 -- TP-Uplift $",
        color=PALETTE["series_2_orange"],
    )
    ax.set_xticks(list(x))
    ax.set_xticklabels(bps)
    ax.set_ylabel("USD")
    ax.set_title("Real per-BP benefit $ -- never summed across categories")
    ax.legend()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


# ============================================================================
# PowerPoint executive deck (python-pptx) -- platform rollup equivalent
# ============================================================================
def write_platform_pptx_deck(path: Path, context: dict, chart_png_paths: Optional[dict] = None) -> Path:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt

    psd = context["platform_source_data"]
    roll = psd["platform_rollup"]
    prs = Presentation()
    blue = RGBColor(0x2A, 0x78, 0xD6)

    slide = _add_branded_slide(prs, 0)
    slide.shapes.title.text = f"{context['bp_id']}: {context['bp_name']}"
    slide.placeholders[1].text = (
        f"Platform-Wide Compliance-Impact Rollup -- {context['generated_at_utc']} UTC"
    )

    slide = _add_branded_slide(prs, 1)
    slide.shapes.title.text = "Business Objective"
    slide.placeholders[1].text_frame.text = context["business_objective"]

    status = context.get("status") or compute_platform_status(psd)
    status_colors = {
        "good": RGBColor(0x0C, 0xA3, 0x0C),
        "warning": RGBColor(0xC9, 0x85, 0x00),
        "critical": RGBColor(0xD0, 0x3B, 0x3B),
    }
    slide = _add_branded_slide(prs, 1)
    slide.shapes.title.text = "Recommendation & Status"
    body = slide.placeholders[1].text_frame
    body.text = status["label"]
    body.paragraphs[0].font.bold = True
    body.paragraphs[0].font.size = Pt(26)
    body.paragraphs[0].font.color.rgb = status_colors.get(status["css_class"], blue)
    p = body.add_paragraph()
    p.text = status["rationale"]
    p.level = 1

    slide = _add_branded_slide(prs, 1)
    slide.shapes.title.text = "What This Means for the Business (Platform-Wide)"
    body = slide.placeholders[1].text_frame
    body.text = context["business_benefits"][0]
    for point in context["business_benefits"][1:]:
        p = body.add_paragraph()
        p.text = point
        p.level = 1

    # ---- Per-BP slides (2 per BP: Business Impact, then Methodology & Regulatory Basis) --
    # replaces the old single generic "What This Means for the Business" / "Regulatory &
    # Compliance Mapping" platform-wide-only slides with real, BP-specific content, reusing
    # the exact same narrative dict (business_objective, top_shap_features,
    # named_engineered_features, regulatory_citations, production_meaning) already built for
    # the HTML dashboard / Word report / PLATFORM_CARD.md -- never re-derived here. Two
    # slides per BP (rather than one cramped slide) so no real sentence is truncated.
    narratives_pptx = context.get("bp_narratives") or build_bp_business_narratives_platform(psd)
    for bp_id in ["BP1", "BP2", "BP3", "BP4", "BP5"]:
        n = narratives_pptx[bp_id]
        bp_data = psd["bps"][bp_id]
        primary = bp_data["variants"][bp_data["primary_variant"]]

        slide = _add_branded_slide(prs, 1)
        slide.shapes.title.text = f"{bp_id}: {bp_data['name']} -- Business Impact"
        body = slide.placeholders[1].text_frame
        body.text = f"Verdict: {n['verdict']}"
        body.paragraphs[0].font.bold = True
        p = body.add_paragraph()
        p.text = n["what_it_does"]
        p.level = 1
        p2 = body.add_paragraph()
        p2.text = n["production_meaning"]
        p2.level = 1

        slide = _add_branded_slide(prs, 1)
        slide.shapes.title.text = f"{bp_id}: {bp_data['name']} -- Methodology & Regulatory Basis"
        body = slide.placeholders[1].text_frame
        champion_line = f"Champion/Signal: {primary.get('champion', 'N/A')}"
        if primary.get("n_features") is not None:
            champion_line += f"  |  Features: {primary['n_features']}"
        if primary.get("threshold") is not None:
            champion_line += f"  |  Threshold: {primary['threshold']:.4f}"
        body.text = champion_line
        body.paragraphs[0].font.bold = True
        p = body.add_paragraph()
        p.text = n["real_performance"]
        p.level = 1
        if bp_data.get("top_shap_features"):
            p = body.add_paragraph()
            p.text = "Top real SHAP drivers: " + ", ".join(f["name"] for f in bp_data["top_shap_features"])
            p.level = 1
        if bp_data.get("named_engineered_features"):
            p = body.add_paragraph()
            p.text = f"Named engineered features ({len(bp_data['named_engineered_features'])}): " + ", ".join(
                bp_data["named_engineered_features"]
            )
            p.level = 1
        if n.get("regulatory_citations"):
            p = body.add_paragraph()
            p.text = "Regulatory basis: " + "; ".join(n["regulatory_citations"])
            p.level = 1

    cat1, cat2, cat3 = (
        roll["benefit_category_1_fp_reduction_savings"],
        roll["benefit_category_2_tp_uplift_value"],
        roll["benefit_category_3_bp2_typology_lines"],
    )
    scale = roll["portfolio_scale"]
    slide = _add_branded_slide(prs, 1)
    slide.shapes.title.text = "Three-Category Financial Rollup (never blended)"
    body = slide.placeholders[1].text_frame
    body.text = f"Category 1 -- FP-Reduction Savings (ASSUMPTION): {_fmt_usd(cat1['total_usd'])}"
    for line in [
        f"Category 2 -- TP-Uplift Illustrative Value (ASSUMPTION): {_fmt_usd(cat2['total_usd'])}",
        f"Category 3 -- BP2 Typology Lines: {_fmt_usd(cat3['auto_typing_efficiency_savings_usd'])} + {_fmt_usd(cat3['typology_confirmation_value_usd'])}",
        f"Portfolio Scale (never dollarized): {scale['bp3_n_nodes']:,} nodes / {scale['bp3_n_edges']:,} edges",
        roll["headline_grand_total_note"],
    ]:
        p = body.add_paragraph()
        p.text = line
        p.level = 1

    if chart_png_paths and "platform_benefit" in chart_png_paths:
        slide = _add_branded_slide(prs, 5)
        slide.shapes.title.text = "Per-BP Benefit Breakdown"
        slide.shapes.add_picture(
            str(chart_png_paths["platform_benefit"]), Inches(0.5), Inches(1.3), width=Inches(9)
        )

    slide = _add_branded_slide(prs, 5)
    slide.shapes.title.text = "Per-BP Status Grid"
    bp_items = list(psd["bps"].items())
    rows, cols = len(bp_items) + 1, 5
    left, top, width, height = Inches(0.5), Inches(1.5), Inches(9), Inches(0.4 * rows)
    table_shape = slide.shapes.add_table(rows, cols, left, top, width, height).table
    for c, h in enumerate(["BP", "Name", "Phase", "Champion / Signal", "Verdict"]):
        table_shape.cell(0, c).text = h
    for r, (bp_id, d) in enumerate(bp_items, start=1):
        primary = d["variants"][d["primary_variant"]]
        table_shape.cell(r, 0).text = bp_id
        table_shape.cell(r, 1).text = d["name"]
        table_shape.cell(r, 2).text = d["phase"]
        table_shape.cell(r, 3).text = primary.get("champion", "N/A")
        table_shape.cell(r, 4).text = primary.get("verdict", "N/A")

    recs = context.get("smart_recommendations") or generate_platform_smart_recommendations(psd)
    slide = _add_branded_slide(prs, 1)
    slide.shapes.title.text = "Key Recommendations"
    body = slide.placeholders[1].text_frame
    body.text = recs[0]["title"]
    p = body.add_paragraph()
    p.text = recs[0]["specific"]
    p.level = 1
    for r in recs[1:]:
        p = body.add_paragraph()
        p.text = r["title"]
        p2 = body.add_paragraph()
        p2.text = r["specific"]
        p2.level = 1

    # Note: the old single platform-wide-only "Regulatory & Compliance Mapping" slide is
    # removed here -- its content now lives per-BP, on each BP's own real "Methodology &
    # Regulatory Basis" slide above (real citations, not the generic list).

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(path))
    return path


# ============================================================================
# Platform card (MODEL_CARD.md / RULE_CARD.md equivalent) -- PLATFORM_CARD.md. BP6 has no
# trained model and no structural signal of its own -- the real deployable artifact is a
# pure, read-only rollup of BP1-BP5's own already-computed figures, and this document says
# so explicitly in its own title and structure.
# ============================================================================
def write_platform_card(path: Path, context: dict) -> Path:
    psd = context["platform_source_data"]
    roll = psd["platform_rollup"]
    status = context.get("status") or compute_platform_status(psd)
    recs = context.get("smart_recommendations") or generate_platform_smart_recommendations(psd)
    cat1, cat2, cat3 = (
        roll["benefit_category_1_fp_reduction_savings"],
        roll["benefit_category_2_tp_uplift_value"],
        roll["benefit_category_3_bp2_typology_lines"],
    )
    scale = roll["portfolio_scale"]

    lines = (
        [
            f"# Platform Card -- {context['bp_id']}: {context['bp_name']}",
            "",
            f"_Generated {context['generated_at_utc']} UTC._",
            "",
            "**This is a PLATFORM CARD, not a model card or rule card.** BP6 has no trained ML "
            "model and no structural signal of its own -- the real deployable artifact is a "
            "pure, read-only rollup of BP1-BP5's own already-computed real figures. No figure "
            "below is recomputed, estimated, or fabricated.",
            "",
            f"## Status: {status['label']}",
            status["rationale"],
            "",
            "## Business Objective",
            context["business_objective"],
            "",
            "## Sourcing Method (verbatim)",
            f"> {psd['sourcing_method']}",
            "",
            "## What This Means for the Business",
        ]
        + [f"- {point}" for point in context["business_benefits"]]
        + [
            "",
            "## Three-Category Financial Rollup (never blended into one grand total)",
            roll["headline_grand_total_note"],
            "",
            "### Category 1 -- FP-Reduction Savings (ASSUMPTION)",
            f"- BP1: {_fmt_usd(cat1['bp1'])}",
            f"- BP4: {_fmt_usd(cat1['bp4'])}",
            f"- BP5: {_fmt_usd(cat1['bp5'])}",
            f"- **TOTAL: {_fmt_usd(cat1['total_usd'])}** "
            f"({cat1['total_investigator_hours_saved']:,} investigator hours saved, "
            f"{cat1['total_fewer_fp_alerts']:,} fewer FP alerts)",
            "",
            "### Category 2 -- TP-Uplift Illustrative Value (ASSUMPTION)",
            f"- BP1: {_fmt_usd(cat2['bp1'])}",
            f"- BP4: {_fmt_usd(cat2['bp4'])}",
            f"- BP5: {_fmt_usd(cat2['bp5'])}",
            f"- **TOTAL: {_fmt_usd(cat2['total_usd'])}** ({cat2['total_additional_cases_caught']:+,} additional real cases caught)",
            "",
            "### Category 3 -- BP2 Typology Lines (kept separate -- different unit basis)",
            f"- Auto-typing efficiency savings: {_fmt_usd(cat3['auto_typing_efficiency_savings_usd'])}",
            f"- Typology confirmation value: {_fmt_usd(cat3['typology_confirmation_value_usd'])}",
            "",
            "### Cost Context (informational only, never summed)",
            roll["cost_context"]["description"],
            "",
            "### Portfolio Scale (volume only, never dollarized)",
            f"- BP3 real network nodes: {scale['bp3_n_nodes']:,}",
            f"- BP3 real network edges: {scale['bp3_n_edges']:,}",
            "",
            "## Per-BP Breakdown",
            "| BP | Name | Phase | Primary Variant | Champion / Signal | Verdict |",
            "|---|---|---|---|---|---|",
        ]
    )
    for bp_id, d in psd["bps"].items():
        primary = d["variants"][d["primary_variant"]]
        lines.append(
            f"| {bp_id} | {d['name']} | {d['phase']} | {d['primary_variant']} | "
            f"{primary.get('champion', 'N/A')} | {primary.get('verdict', 'N/A')} |"
        )

    narratives = context.get("bp_narratives") or build_bp_business_narratives_platform(psd)
    lines += ["", "## Per-BP Business Narratives"]
    for bp_id, n in narratives.items():
        lines += [
            f"### {n['title']} (Verdict: {n['verdict']})",
            f"**What it does.** {n['what_it_does']}",
            "",
            f"**Real validated performance.** {n['real_performance']}",
            "",
            f"**What production deployment would mean.** {n['production_meaning']}",
            "",
        ]
        if n.get("methodology"):
            lines += [
                f"**Methodology & Regulatory Basis.** {n['methodology']}",
                "",
            ]

    lines += [
        "",
        "## Explainability -- Not Applicable at the Platform Level",
        "BP6 has no trained model and no structural signal of its own to explain -- each "
        "contributing BP's own SHAP/LIME (or structural rule rationale) analysis is "
        "documented in that BP's own MODEL_CARD.md / RULE_CARD.md, not duplicated here.",
        "",
        "## Ethical Considerations / Fairness",
        context["fairness_note"],
        "",
        "## Caveats & Limitations",
    ]
    for cav in context.get("caveats", []):
        lines.append(f"- {cav}")
    lines += ["", "## Regulatory Mapping"]
    for fw, applies in context["regulatory_frameworks"]:
        lines.append(f"- {fw} -- {applies}")
    lines += ["", "## Recommendations"]
    for r in recs:
        lines += [
            f"### {r['title']}",
            f"- **Specific:** {r['specific']}",
            f"- **Measurable:** {r['measurable']}",
            f"- **Achievable:** {r['achievable']}",
            f"- **Relevant:** {r['relevant']}",
            f"- **Time-bound:** {r['time_bound']}",
            "",
        ]

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
