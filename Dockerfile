# syntax=docker/dockerfile:1

# JobPilot runtime image. Includes Chromium + its OS dependencies so the
# Application agent can drive real application forms. For a smaller image that
# only uses the simulated browser, drop the `playwright install` line and set
# JOBPILOT_BROWSER_MODE=simulated.
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    JOBPILOT_LOG_FORMAT=json \
    JOBPILOT_BROWSER_HEADLESS=true \
    JOBPILOT_ARTIFACTS_DIR=/app/artifacts

WORKDIR /app

# Install the package first (best layer caching for dependencies).
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install .

# Install the Chromium browser and its system libraries.
RUN playwright install --with-deps chromium

COPY data ./data

# Run as a non-root user; keep the artifacts dir writable.
RUN useradd --create-home --uid 10001 jobpilot \
    && mkdir -p /app/artifacts \
    && chown -R jobpilot:jobpilot /app
USER jobpilot

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

CMD ["uvicorn", "jobpilot.main:app", "--host", "0.0.0.0", "--port", "8000"]
