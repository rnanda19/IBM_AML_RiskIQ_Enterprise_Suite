# Contributing

This is an independent portfolio project, built and run by one person -- see the Execution boundary
section of `README.md` -- it isn't currently seeking external code contributions.

If you spot a real bug, a factual error, or a broken link, please open a GitHub issue describing it. Pull
requests are welcome for typo fixes and documentation clarity, but any change to notebook logic, model
code, or reported numbers has to go through this project's own standing rule: the change is proposed, the
owner runs it for real on their own machine, and the result is recorded in `LESSONS_LEARNED_APPLIED.md` and
`docs/evidence_ledger/EVIDENCE_LEDGER.md` before it's considered part of this project's real, confirmed
state -- no reported metric here is ever carried forward from a claim or a prior run without a fresh,
on-disk artifact backing it (the project's zero-fabrication discipline).

## Reporting a bug
Open a GitHub issue with: what you expected, what happened instead, and which BP (business problem) and
file it's in. If it's a security issue, see `SECURITY.md` instead of opening a public issue.

## Code style
`black` (line length 110), `isort` (black profile), `flake8`, and `mypy` are all enforced in CI
(`.github/workflows/ci.yml`) and `pre-commit` (`.pre-commit-config.yaml`). Run `make test-all` locally
before opening a PR.
