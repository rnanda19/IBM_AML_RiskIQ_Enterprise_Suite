# Baseline Test Report

Real command output, captured 2026-10-10 during Phase 1 audit. Every command below was actually run in
this session against the repository as it currently stands (commit `bcad324` and the uncommitted changes
from this audit pass). Nothing here is copied from an older run or a README claim.

## pytest (full suite)

```
$ python3 -m pytest tests/ -q
66 passed, 1 warning in 4.62s
```

25 unit (`tests/unit/`), 41 integration (`tests/integration/<bp>/`). The 1 warning is a known
`StarletteDeprecationWarning` about `httpx` vs `httpx2` in `starlette.testclient` -- not a test failure,
not something this project's code controls.

## flake8

```
$ python3 -m flake8 src/ tests/
(no output -- clean)
```

## black --check

```
$ python3 -m black --check src/ tests/ --target-version py310
All done! (23 files left unchanged)
```

## isort --check-only

```
$ python3 -m isort --check-only src/ tests/
(no output -- clean)
```

## mypy

```
$ python3 -m mypy src/
Success: no issues found in 16 source files
```

## bandit

```
$ python3 -m bandit -r src/ -x src/docker -q
Total lines of code: 7608
Total issues (by severity): Low: 7, Medium: 0, High: 0
Total issues (by confidence): High: 7
```
All 7 Low/High-confidence findings are the `pickle.load` calls each scoring service uses on its own
trusted, self-produced model artifact -- each is individually `# nosec B301`-annotated with a
trust-boundary justification (confirmed by direct read of `SECURITY.md` and the relevant service files),
not a blanket suppression.

## CI workflow integrity check

Direct read of all 5 workflow files in `.github/workflows/` confirms no step uses `|| true` (or any
other always-succeed suppression) on a lint, type-check, security-scan, or test step. This was a real,
fixed regression earlier this session (commit `bcad324`) -- flagged here as still-clean after that fix.

## Known-failing / known-excluded (not attempted, documented why)

- **BP2 Docker build+run**: known to crash on startup (DEF-001 in `DEFECT_REGISTER.md`). Not re-attempted
  in this baseline pass since the root cause (stale validation report missing a key) is already confirmed
  by `docker-verify.yml`'s own header comment and `ROADMAP.md`; re-running would reproduce the same known
  `KeyError`.
- **BP3 Docker build+run**: known to be missing a required artifact (DEF-002). Same reasoning -- not
  re-attempted.
- **Real end-to-end notebook re-execution (any BP)**: not attempted. Per this project's standing
  no-pipeline-execution rule (see `INITIAL_REPOSITORY_AUDIT.md`), I do not run
  `02_feature_engineering_modeling`/`03_statistical_validation_deployment` against the real dataset
  myself. This baseline report covers code-level checks (tests, lint, type, security) only -- it is not a
  re-validation of the reported model metrics in `BENCHMARKS.md`.

## Environment note

All commands above were run inside the user's own Windows-hosted development VM (the project's working
Python environment, with `requirements.txt` already installed), not a freshly provisioned clean
environment. A true from-clean-clone reproduction (Prompt 7's ask) has not yet been attempted in this
audit pass.
