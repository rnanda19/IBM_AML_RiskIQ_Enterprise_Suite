# BP4 Structuring & Smurfing Detection -- deployable scoring service
# Build context: this Dockerfile expects to be built with the repository root as build
# context (docker build -f src/docker/bp4_structuring_smurfing_detection/Dockerfile .),
# so the COPY paths below are relative to the repo root, not this Dockerfile's own folder.
# Real champion model file (generated 2026-10-01T16:42:51.285856+00:00,
# variant LI-Medium) is copied in explicitly below -- never defaulted to a path that
# isn't actually present in the image.
#
# DISCLOSED GAP: src/services/bp4_scoring_service.py does not yet exist on disk as of this
# notebook's run (same gap already flagged for BP3) -- it must be extracted from Notebook 3's
# in-kernel score_transaction()/FastAPI app before this image will actually build and run.
FROM python:3.11-slim

WORKDIR /app

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

EXPOSE 8001
CMD ["uvicorn", "src.aml_riskiq.serving.bp4_scoring_service:app", "--host", "0.0.0.0", "--port", "8001"]
