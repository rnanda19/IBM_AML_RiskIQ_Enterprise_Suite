# BP4 Structuring & Smurfing Detection -- deployable scoring service
# Build context: this Dockerfile expects to be built with the repository root as build
# context (docker build -f src/docker/bp4_structuring_smurfing_detection/Dockerfile .),
# so the COPY paths below are relative to the repo root, not this Dockerfile's own folder.
# Real champion model file (generated 2026-10-01T16:42:51.285856+00:00,
# variant LI-Medium) is copied in explicitly below -- never defaulted to a path that
# isn't actually present in the image.
#
# RESOLVED: src/aml_riskiq/serving/bp4_scoring_service.py exists and this image is build+run
# verified in CI (.github/workflows/docker-verify.yml) -- the comment this replaces was stale
# (described a gap that no longer exists as of this edit).
#
# PORT FIX (this session): this service previously shared port 8001 with BP2 -- a real
# collision if both were ever run together (confirmed: both Dockerfiles EXPOSEd 8001, both
# docker-compose.yml files mapped host port 8001:8001). Moved to 8004 -- the first port not
# already claimed by BP1 (8000), BP2 (8001), BP3 (8003), or BP5 (8002).
FROM python:3.11-slim

WORKDIR /app

# Secure container default: refuse startup unless API keys are configured.
ENV AML_RISKIQ_REQUIRE_AUTH=true

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt fastapi uvicorn

COPY src/ ./src/
COPY models/bp4_structuring_smurfing_detection/bp4_notebook3_champion_li_medium.pkl \
     ./models/bp4_structuring_smurfing_detection/bp4_notebook3_champion_li_medium.pkl

# FOUND + FIXED (2026-10-02, hardening pass): this image never copied the real saved
# validation-report JSON into /app/reports/ -- the service module reads its
# feature_cols/threshold/champion_name etc. from that exact file at import time and
# raises FileNotFoundError if it is missing, so this image would have built "successfully"
# and then crashed on every container start. Copied in explicitly below, same discipline as
# the model artifact above.
COPY reports/bp4_structuring_smurfing_detection/bp4_notebook3_validation_report_li_medium.json \
     ./reports/bp4_structuring_smurfing_detection/bp4_notebook3_validation_report_li_medium.json

ENV BP4_CHAMPION_MODEL_PATH=/app/models/bp4_structuring_smurfing_detection/bp4_notebook3_champion_li_medium.pkl
ENV BP4_DATASET_VARIANT=LI-Medium

# Hardening (this session): run as a non-root user, and give Docker's own HEALTHCHECK
# visibility into the real /health endpoint this service already exposes -- previously only
# docker-verify.yml's own curl polling loop checked it; now the image reports its own health
# natively too (docker ps / a real orchestrator's liveness probe can both use it).
RUN addgroup --system app && adduser --system --ingroup app app \
    && chown -R app:app /app
USER app

EXPOSE 8004
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8004/health', timeout=2)" || exit 1
CMD ["uvicorn", "src.aml_riskiq.serving.bp4_scoring_service:app", "--host", "0.0.0.0", "--port", "8004"]
