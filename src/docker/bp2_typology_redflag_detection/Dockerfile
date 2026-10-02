# BP2 Typology & Red-Flag Pattern Detection -- deployable scoring service
# Build context: this Dockerfile expects to be built with the repository root as build
# context (docker build -f src/docker/bp2_typology_redflag_detection/Dockerfile .),
# so the COPY paths below are relative to the repo root, not this Dockerfile's own folder.
# Real champion model + label encoder files (generated 2026-10-01T08:00:27.273774+00:00,
# variant LI-Medium) are copied in explicitly below -- never defaulted to a path
# that isn't actually present in the image (the real bug this comment exists to prevent).
# RESOLVED (2026-10-02): src/services/bp2_scoring_service.py now exists, mirroring
# Notebook 3's own real, self-tested FastAPI app (score_transaction / app / score_endpoint)
# verbatim. Notebook 3 was also hardened the same day to persist the real train-median
# impute value for its one disclosed NaN-prone column (amount_paid_received_ratio) as
# champion_needs_rf_impute / rf_impute_value in its saved validation report -- this image
# will only serve real-valued impute logic once BP2 Notebook 3 has been RE-RUN for the
# LI-Medium variant to regenerate that report with the two new keys.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt fastapi uvicorn

COPY src/ ./src/
COPY models/bp2_typology_redflag_detection/bp2_notebook3_champion_li_medium.pkl \
     ./models/bp2_typology_redflag_detection/bp2_notebook3_champion_li_medium.pkl
COPY models/bp2_typology_redflag_detection/bp2_notebook3_label_encoder_li_medium.pkl \
     ./models/bp2_typology_redflag_detection/bp2_notebook3_label_encoder_li_medium.pkl

# FOUND + FIXED (2026-10-02, hardening pass): this image never copied the real saved
# validation-report JSON into /app/reports/ -- the service module reads its
# feature_cols/threshold/champion_name etc. from that exact file at import time and
# raises FileNotFoundError if it is missing, so this image would have built "successfully"
# and then crashed on every container start. Copied in explicitly below, same discipline as
# the model artifact above.
COPY reports/bp2_typology_redflag_detection/bp2_notebook3_validation_report_li_medium.json \
     ./reports/bp2_typology_redflag_detection/bp2_notebook3_validation_report_li_medium.json

ENV BP2_CHAMPION_MODEL_PATH=/app/models/bp2_typology_redflag_detection/bp2_notebook3_champion_li_medium.pkl
ENV BP2_LABEL_ENCODER_PATH=/app/models/bp2_typology_redflag_detection/bp2_notebook3_label_encoder_li_medium.pkl
ENV BP2_DATASET_VARIANT=LI-Medium

EXPOSE 8001
CMD ["uvicorn", "src.services.bp2_scoring_service:app", "--host", "0.0.0.0", "--port", "8001"]
