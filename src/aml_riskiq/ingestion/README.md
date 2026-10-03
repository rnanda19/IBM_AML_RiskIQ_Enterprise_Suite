# src/aml_riskiq/ingestion/
Honest placeholder (same convention as this package's `features/`, `models/`, and `typology/` modules
when first scaffolded): there is no standalone, importable data-loading module here yet. Today, every
BP's Notebook 1/2 reads its own real source files directly --
`data/raw/{HI,LI}-{Small,Medium,Large}_{Trans,accounts}.{csv,parquet}` and the matching `_Patterns.txt`
label files, sourced from `github.com/IBM/AML-Data` (see `DATA_PRIVACY.md` / README.md's Dataset section)
-- inline in each notebook's own cells, not through a shared loader class.

The one real, shared surface that exists today is `src/aml_riskiq/utils/project_root.py`'s
`raw_data_dir()` -- a thin, already-used helper that resolves the real on-disk `data/raw/` directory
(env override -> marker-file walk-up -> well-known locations), so every notebook and service agrees on
where real data lives without hard-coding a path. It is not a loader; it does not read, parse, or cache
any file.

## What would go here
A real `ingestion/` module -- shared Polars/pandas readers for the raw CSV/Parquet + Patterns-label
files, with real schema validation -- would deduplicate logic that is currently copy-pasted across 6 BPs'
Notebook 1/2 cells (a real, disclosed gap, not a hidden one). Extracting it is future work; this
directory exists now so the package's real intended shape (`ingestion/graph/features/models/
explainability/serving`) is visible even before every module has real content, consistent with how
`features/`, `models/`, and `typology/` were scaffolded.
