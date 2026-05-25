FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/src \
    PORT=8000 \
    DB_PATH=/data/running-portal/portal.db \
    MI_FITNESS_STATE_PATH=/data/running-portal/auth.json \
    MI_FITNESS_CACHE_DIR=/data/running-portal/fds_cache

WORKDIR /app

RUN addgroup --system app && \
    adduser --system --ingroup app --home /app app && \
    mkdir -p /data/running-portal && \
    chown -R app:app /app /data/running-portal

COPY pyproject.toml README.md ./
COPY portal ./portal
COPY src ./src
COPY static ./static
COPY templates ./templates

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\", \"8000\")}/', timeout=3).read(1)"

CMD ["sh", "-c", "uvicorn portal.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
