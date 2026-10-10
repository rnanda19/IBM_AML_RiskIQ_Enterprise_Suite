# BP6 Enterprise AML Compliance Monitoring & Regulatory Reporting -- platform rollup batch job
# Build context: this Dockerfile expects to be built with the repository root as build
# context (docker build -f src/docker/bp6_enterprise_compliance_monitoring/Dockerfile .),
# so the COPY paths below are relative to the repo root, not this Dockerfile's own folder.
#
# IMPORTANT -- this is NOT a scoring API, unlike BP1/BP3/BP4/BP5's Docker images. BP6 has no
# trained model and no structural signal of its own to score with -- it is a pure, read-only
# rollup of BP1-BP5's own already-computed real figures. This image runs BP6's own reporting
# pipeline (the extractor script + Notebooks 2-4's logic) as a ONE-SHOT BATCH JOB against the
# real BP1-BP5 report artifacts mounted in via the `reports/` volume, and writes its own real
# five-format executive package back out to that same mounted volume. No port is exposed --
# there is nothing to serve.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY notebooks/bp6_enterprise_compliance_monitoring/ ./notebooks/bp6_enterprise_compliance_monitoring/
COPY PROJECT_STRUCTURE_LOCKED.md .

ENV AML_RISKIQ_SUITE_ROOT=/app

# Runs the one consolidated notebook end-to-end and writes its executed copy back out --
# per the user's explicit 2026-10-02 "only one ipynb" request, BP6's reporting pipeline is
# authored as a single real .ipynb, not 4 separate .py scripts (see
# the committed notebook filename and LESSONS_LEARNED_APPLIED.md). Dependencies include
# nbformat, nbconvert, and ipykernel. The dedicated GitHub Actions workflow builds this image,
# executes the notebook against committed report/model artifacts, and checks required outputs.
CMD ["jupyter", "nbconvert", "--to", "notebook", "--execute", "--inplace", \
     "notebooks/bp6_enterprise_compliance_monitoring/IBM AML RiskIQ Enterprise Suite 00_Executive_Rollup_Report.ipynb"]
