# Case Management Service -- deployable RBAC-protected case-management API, wiring the
# casework/ package (alert schema, lifecycle state machine, SQLite-backed store) into live
# routes. Added 2026-10-12 to close DEF-003 ("No RBAC at the API layer") -- see
# docs/audit/DEFECT_REGISTER.md and docs/security/RBAC.md.
#
# Build context: this Dockerfile expects to be built with the repository root as build
# context (docker build -f src/docker/case_management/Dockerfile .), same convention as
# every BP1-BP5 scoring service's own Dockerfile -- COPY paths below are relative to the
# repo root, not this Dockerfile's own folder.
#
# Unlike BP1-BP5, this service has no trained model artifact to copy in -- its only real
# dependency is the casework/ package itself (already under src/) and a writable directory
# for its SQLite file, created at runtime by AlertStore's own Path.mkdir(parents=True).
FROM python:3.11-slim

WORKDIR /app

# Secure container default: refuse startup unless API keys are configured -- same fail-closed
# default every BP1-BP5 Dockerfile already sets.
ENV AML_RISKIQ_REQUIRE_AUTH=true
ENV AML_RISKIQ_CASE_DB_PATH=/app/data/case_management/casework.db

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt fastapi uvicorn

COPY src/ ./src/
COPY PROJECT_STRUCTURE_LOCKED.md .

# Non-root user, same hardening every other service's Dockerfile already applies. The data/
# directory is created here (not left to the app's own first-write mkdir) so it is owned by
# `app`, not root, before the process ever starts.
RUN addgroup --system app && adduser --system --ingroup app app \
    && mkdir -p /app/data/case_management \
    && chown -R app:app /app
USER app

EXPOSE 8005
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8005/health', timeout=2)" || exit 1
CMD ["uvicorn", "src.aml_riskiq.serving.case_management_service:app", "--host", "0.0.0.0", "--port", "8005"]
