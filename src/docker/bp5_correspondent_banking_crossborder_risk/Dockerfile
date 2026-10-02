# BP5 Correspondent Banking & Cross-Border Wire Risk -- deployable scoring service
# Build context: this Dockerfile expects to be built with the repository root as build
# context (docker build -f src/docker/bp5_correspondent_banking_crossborder_risk/Dockerfile .),
# so the COPY paths below are relative to the repo root, not this Dockerfile's own folder.
# Real champion model file (generated 2026-10-02T10:40:41.903389+00:00,
# variant LI-Medium) is copied in explicitly below -- never defaulted to a path that
# isn't actually present in the image.
#
# RESOLVED (2026-10-02, hardening pass): src/services/bp5_scoring_service.py has been
# extracted from Notebook 3's in-kernel scoring self-test (score_transaction copied verbatim;
# both variants' real FastAPI self-test already proved it bit-identical to direct batch
# predict_proba -- 5,000 rows checked, 0 mismatches, max_abs_diff=0.0) and its structural
# pytest suite (tests/bp5_correspondent_banking_crossborder_risk/test_bp5_scoring_service.py,
# against a synthetic stub classifier, never this BP's real trained model) passes 5/5. This
# BP's docker-compose.yml build context was also found and fixed in this same pass: it was
# "../../../.." (one level above the real repo root, the exact bug already fixed platform-
# wide for BP1-BP4 but missed here since BP5 had not been hardened yet) -- corrected to
# "../../..", verified via realpath --relative-to against the real repo root.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt fastapi uvicorn

COPY src/ ./src/
COPY models/bp5_correspondent_banking_crossborder_risk/bp5_li_medium_model_v1.pkl \
     ./models/bp5_correspondent_banking_crossborder_risk/bp5_li_medium_model_v1.pkl

# FOUND + FIXED (2026-10-02, hardening pass): this image never copied the real saved
# validation-report JSON into /app/reports/ -- the service module reads its
# feature_cols/threshold/champion_name etc. from that exact file at import time and
# raises FileNotFoundError if it is missing, so this image would have built "successfully"
# and then crashed on every container start. Copied in explicitly below, same discipline as
# the model artifact above.
COPY reports/bp5_correspondent_banking_crossborder_risk/bp5_notebook3_validation_report_li_medium.json \
     ./reports/bp5_correspondent_banking_crossborder_risk/bp5_notebook3_validation_report_li_medium.json

ENV BP5_CHAMPION_MODEL_PATH=/app/models/bp5_correspondent_banking_crossborder_risk/bp5_li_medium_model_v1.pkl
ENV BP5_DATASET_VARIANT=LI-Medium

EXPOSE 8002
CMD ["uvicorn", "src.services.bp5_scoring_service:app", "--host", "0.0.0.0", "--port", "8002"]
