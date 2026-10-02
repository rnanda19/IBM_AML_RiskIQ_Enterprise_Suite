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

ENV BP3_CHAMPION_RULE_PATH=/app/models/bp3_network_graph_intelligence/bp3_notebook3_champion_rule_li_medium.json
ENV BP3_LOOKUP_PATH=/app/models/bp3_network_graph_intelligence/bp3_notebook3_near_train_flagged_lookup_li_medium.parquet
ENV BP3_DATASET_VARIANT=LI-Medium

EXPOSE 8003
CMD ["uvicorn", "src.services.bp3_rule_scoring_service:app", "--host", "0.0.0.0", "--port", "8003"]
