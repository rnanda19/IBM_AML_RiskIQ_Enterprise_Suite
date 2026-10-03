# src/aml_riskiq/reporting/
Shared report_builder module: batched python-docx writer, reused matplotlib figures, vectorized openpyxl
writer with a dedicated Assumptions sheet, and a self-contained Chart.js HTML dashboard builder (bundle
Chart.js locally - do not rely on a CDN, per the that prior lending-risk platform Notebook 01 real-run lesson).
