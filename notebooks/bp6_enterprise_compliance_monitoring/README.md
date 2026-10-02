# 00 - Executive Rollup Report (BP6 - Enterprise AML Compliance Monitoring & Regulatory Reporting)

**Single consolidated notebook** (per explicit user request, 2026-10-02 -- see
`LESSONS_LEARNED_APPLIED.md`): `00_Executive_Rollup_Report.ipynb` contains, as
sequential cells in one real `.ipynb`, all of this BP's work --

1. Business Understanding & Policy (markdown)
2. Phase-Level Aggregation (code)
3. Platform-Level Master Rollup + Structural Validation (code)
4. Compliance-Impact Reporting & Packaging -- this BP's own executive rollup (code)

-- which when run top-to-bottom produces the real five-format executive package
(Word/Excel/HTML/PPTX/PDF) + `PLATFORM_CARD.md` + `CHANGELOG.md` under
`reports/bp6_enterprise_compliance_monitoring/`.

`_extract_platform_source_data.py` is a standalone helper script this notebook reads from
(not itself one of "the notebooks") -- re-run it any time a BP1-BP5 report changes, before
re-running the notebook.

This is the one exception on this platform to the "4 separate notebook files per BP"
convention every other BP (BP1-BP5) follows. The `00` prefix marks it as the master
rollup that precedes/encompasses BP1-5's own numbered notebooks.
