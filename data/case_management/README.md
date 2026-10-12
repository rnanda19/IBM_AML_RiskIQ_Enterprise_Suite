# Case Management Runtime Database

This directory holds `casework.db` -- the SQLite file `src/aml_riskiq/casework/store.py`'s
`AlertStore` creates and writes to at runtime (alerts, case-status history, investigation
notes, evidence references). It is created automatically the first time
`case_management_service.py` starts; nothing here needs to be created by hand.

**Never committed.** `.gitignore` excludes `data/case_management/*.db` for the same reason
`data/raw/`, `data/processed/`, and `data/external/` are excluded: this is real runtime state
produced by running the service, not a project deliverable. This README is committed so the
directory itself (and the reason it's empty in a fresh checkout) is documented.

Override the database path with the `AML_RISKIQ_CASE_DB_PATH` environment variable (see
`src/aml_riskiq/serving/case_management_service.py` and `docs/security/RBAC.md`).
