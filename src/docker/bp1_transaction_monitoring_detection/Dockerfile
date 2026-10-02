# BP1 Transaction Monitoring & Suspicious Activity Detection -- deployable scoring service
# Build context: this Dockerfile expects to be built with the repository root as build
# context (docker build -f src/docker/bp1_transaction_monitoring_detection/Dockerfile .),
# so the COPY paths below are relative to the repo root, not this Dockerfile's own folder.
# Real champion model file (generated 2026-10-01T06:26:36.290830+00:00,
# variant LI-Medium) is copied in explicitly below -- never defaulted to a path that
# isn't actually present in the image (the real bug this comment exists to prevent).
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt fastapi uvicorn

COPY src/ ./src/
COPY models/bp1_transaction_monitoring_detection/bp1_notebook3_champion_li_medium.pkl \
     ./models/bp1_transaction_monitoring_detection/bp1_notebook3_champion_li_medium.pkl

# FOUND + FIXED (2026-10-02, hardening pass): this image never copied the real saved
# validation-report JSON into /app/reports/ -- the service module reads its
# feature_cols/threshold/champion_name etc. from that exact file at import time and
# raises FileNotFoundError if it is missing, so this image would have built "successfully"
# and then crashed on every container start. Copied in explicitly below, same discipline as
# the model artifact above.
COPY reports/bp1_transaction_monitoring_detection/bp1_notebook3_validation_report_li_medium.json \
     ./reports/bp1_transaction_monitoring_detection/bp1_notebook3_validation_report_li_medium.json

ENV BP1_CHAMPION_MODEL_PATH=/app/models/bp1_transaction_monitoring_detection/bp1_notebook3_champion_li_medium.pkl
ENV BP1_DATASET_VARIANT=LI-Medium

EXPOSE 8000
CMD ["uvicorn", "src.services.bp1_scoring_service:app", "--host", "0.0.0.0", "--port", "8000"]
