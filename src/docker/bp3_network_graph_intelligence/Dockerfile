# BP3 Transaction Network & Graph Intelligence -- deployable scoring service
# Build context: this Dockerfile expects to be built with the repository root as build
# context (docker build -f src/docker/bp3_network_graph_intelligence/Dockerfile .),
# so the COPY paths below are relative to the repo root, not this Dockerfile's own folder.
# The real champion artifact (generated 2026-10-01T08:51:30.582280+00:00, variant
# LI-Medium) is a RULE JSON file, never a pickled classifier -- BP3 has no trained ML
# model (see RULE_CARD.md). Copied in explicitly below -- never defaulted to a path that
# isn't actually present in the image (the real bug this comment exists to prevent).
# RESOLVED (2026-10-02): the real, self-tested FastAPI app (score_account / app /
# score_endpoint) has been extracted into a standalone src/services/bp3_rule_scoring_
# service.py module (same closure as BP1's and BP4's own Docker packaging gap). The
# 2-hop-proximity champion signal's real TRAIN-flagged-adjacency membership is now
# persisted alongside the rule JSON as a real per-account near_train_flagged Parquet
# lookup table (Notebook 3's own already-computed near_flagged_ids BFS result, written to
# disk by that notebook's 2026-10-02 hardening addition) -- COPYed in below as
# BP3_LOOKUP_PATH. REMAINING REAL DEPENDENCY, disclosed rather than worked around: that
# lookup Parquet file does not exist on this real on-device project tree until the user
# re-runs 03_statistical_validation_deployment_SINGLE_CELL.py (LI-Medium) ONE MORE TIME
# post-patch -- this image will fail to start with a clear FileNotFoundError until that
# real re-run happens; this Dockerfile does not fabricate a placeholder lookup file.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt fastapi uvicorn

COPY src/ ./src/
COPY models/bp3_network_graph_intelligence/bp3_notebook3_champion_rule_li_medium.json \
     ./models/bp3_network_graph_intelligence/bp3_notebook3_champion_rule_li_medium.json
COPY models/bp3_network_graph_intelligence/bp3_notebook3_near_train_flagged_lookup_li_medium.parquet \
     ./models/bp3_network_graph_intelligence/bp3_notebook3_near_train_flagged_lookup_li_medium.parquet

# FOUND + FIXED (2026-10-02, hardening pass): this image never copied the real saved
# validation-report JSON into /app/reports/ -- the service module reads its
# feature_cols/threshold/champion_name etc. from that exact file at import time and
# raises FileNotFoundError if it is missing, so this image would have built "successfully"
# and then crashed on every container start. Copied in explicitly below, same discipline as
# the model artifact above.
COPY reports/bp3_network_graph_intelligence/bp3_notebook3_validation_report_li_medium.json \
     ./reports/bp3_network_graph_intelligence/bp3_notebook3_validation_report_li_medium.json

ENV BP3_CHAMPION_RULE_PATH=/app/models/bp3_network_graph_intelligence/bp3_notebook3_champion_rule_li_medium.json
ENV BP3_LOOKUP_PATH=/app/models/bp3_network_graph_intelligence/bp3_notebook3_near_train_flagged_lookup_li_medium.parquet
ENV BP3_DATASET_VARIANT=LI-Medium

# Hardening (this session): run as a non-root user, and give Docker's own HEALTHCHECK
# visibility into the real /health endpoint this service already exposes -- previously only
# docker-verify.yml's own curl polling loop checked it; now the image reports its own health
# natively too (docker ps / a real orchestrator's liveness probe can both use it).
RUN addgroup --system app && adduser --system --ingroup app app \
    && chown -R app:app /app
USER app

EXPOSE 8003
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8003/health', timeout=2)" || exit 1
CMD ["uvicorn", "src.aml_riskiq.serving.bp3_rule_scoring_service:app", "--host", "0.0.0.0", "--port", "8003"]
