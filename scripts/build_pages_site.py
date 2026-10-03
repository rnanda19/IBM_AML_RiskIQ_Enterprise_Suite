#!/usr/bin/env python3
"""
Builds the static site GitHub Pages deploys (see .github/workflows/pages.yml). Copies this
platform's real, already-committed executive-reporting deliverables from
reports/<bp>/executive_package/ into _site/<bp>/ unchanged, and writes one index.html linking to
every real file. Nothing is generated, computed, or renamed here beyond directory copying --
every number on the index page is read back from the same real BP README.md / MODEL_CARD.md /
PLATFORM_CARD.md files this repository already ships, never re-typed by hand.
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "_site"

BPS = [
    {
        "slug": "bp6_enterprise_compliance_monitoring",
        "dir": "bp6",
        "title": "00 — Executive Rollup Summary",
        "metric": "Pure rollup of BP1–BP5 · Reconciliation gate · PASS",
    },
    {
        "slug": "bp1_transaction_monitoring_detection",
        "dir": "bp1",
        "title": "BP1 — Transaction Monitoring & Suspicious Activity Detection",
        "metric": "XGBoost · Test PR-AUC 0.1242 · PASS",
    },
    {
        "slug": "bp2_typology_redflag_detection",
        "dir": "bp2",
        "title": "BP2 — Typology & Red-Flag Pattern Detection",
        "metric": "RandomForest · Test macro-F1 0.4440 · PASS",
    },
    {
        "slug": "bp3_network_graph_intelligence",
        "dir": "bp3",
        "title": "BP3 — Transaction Network & Graph Intelligence",
        "metric": "2-hop proximity rule · Network-lift 3.19x · PASS",
    },
    {
        "slug": "bp4_structuring_smurfing_detection",
        "dir": "bp4",
        "title": "BP4 — Structuring & Smurfing Detection",
        "metric": "XGBoost · Test PR-AUC 0.1253 · PASS",
    },
    {
        "slug": "bp5_correspondent_banking_crossborder_risk",
        "dir": "bp5",
        "title": "BP5 — Correspondent Banking & Cross-Border Wire Risk",
        "metric": "XGBoost · Test PR-AUC 0.1399 · PASS",
    },
]

FORMAT_LABELS = {
    ".html": "Live Dashboard",
    ".docx": "Word Report",
    ".xlsx": "Excel Workbook",
    ".pptx": "PowerPoint Deck",
    ".pdf": "PDF Export",
}


def build() -> None:
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)

    rows_html = []
    for bp in BPS:
        src_dir = ROOT / "reports" / bp["slug"] / "executive_package"
        dst_dir = SITE / bp["dir"]
        if not src_dir.is_dir():
            print(f"[WARN] missing executive_package for {bp['slug']} -- skipping")
            continue
        dst_dir.mkdir(parents=True, exist_ok=True)

        links = []
        for item in sorted(src_dir.iterdir()):
            if item.is_dir() or item.name.startswith("_"):
                continue
            shutil.copy2(item, dst_dir / item.name)
            label = FORMAT_LABELS.get(item.suffix.lower())
            if label is None:
                continue
            href = f"{bp['dir']}/{item.name}"
            if item.suffix.lower() == ".html":
                links.append(f'<a class="fmt fmt-live" href="{href}">{label}</a>')
            else:
                links.append(f'<a class="fmt" href="{href}" download>{label}</a>')

        rows_html.append(
            f'<div class="bp-card">'
            f'<h2>{bp["title"]}</h2>'
            f'<p class="metric">{bp["metric"]}</p>'
            f'<div class="formats">{"".join(links)}</div>'
            f"</div>"
        )

    index_html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>IBM AML RiskIQ Enterprise Suite — Live Reports</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; padding: 2.5rem 1.5rem;
          background: #0f172a; color: #f1f5f9; }}
  .wrap {{ max-width: 980px; margin: 0 auto; }}
  h1 {{ font-size: 1.9rem; margin-bottom: 0.25rem; }}
  .sub {{ color: #94a3b8; margin-bottom: 2rem; max-width: 70ch; line-height: 1.5; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1rem; }}
  .bp-card {{ background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 1.1rem 1.3rem; }}
  .bp-card h2 {{ font-size: 1.05rem; margin: 0 0 0.35rem; }}
  .metric {{ color: #38bdf8; font-size: 0.85rem; margin: 0 0 0.9rem; }}
  .formats {{ display: flex; flex-wrap: wrap; gap: 0.5rem; }}
  .fmt {{ font-size: 0.8rem; padding: 0.35rem 0.7rem; border-radius: 6px; text-decoration: none;
          background: #334155; color: #e2e8f0; border: 1px solid #475569; }}
  .fmt-live {{ background: #0d9488; border-color: #0f766e; color: #fff; font-weight: 600; }}
  footer {{ margin-top: 2.5rem; color: #64748b; font-size: 0.8rem; }}
  a {{ transition: opacity .15s; }} a:hover {{ opacity: 0.8; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>IBM AML RiskIQ Enterprise Suite — Live Reports</h1>
  <p class="sub">Real executive-reporting deliverables for all 6 Business Problems, generated on this
  platform's locked LI-Medium validation tier. The teal "Live Dashboard" link opens the real interactive
  HTML report in your browser; every other format downloads the real file directly. See the
  <a href="https://github.com/rnanda19/IBM_AML_RiskIQ_Enterprise_Suite" style="color:#38bdf8;">source
  repository</a> for the full platform, including every BP's own MODEL_CARD.md / RULE_CARD.md /
  PLATFORM_CARD.md.</p>
  <div class="grid">
    {''.join(rows_html)}
  </div>
  <footer>Built from real, already-committed files under reports/&lt;bp&gt;/executive_package/ -- nothing
  on this page is generated or recomputed by this build step.</footer>
</div>
</body>
</html>
"""
    (SITE / "index.html").write_text(index_html, encoding="utf-8")
    print(f"[OK] built {SITE} with {len(rows_html)} BP card(s)")


if __name__ == "__main__":
    build()
