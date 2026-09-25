FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    LITTORA_DATA_DIR=/data \
    LITTORA_REPORTS_DIR=/reports \
    LITTORA_STORAGE_DIR=/storage

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libexpat1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app
COPY config ./config
RUN pip install . \
    && useradd --create-home --uid 10001 littora \
    && mkdir -p /storage \
    && chown littora /storage

USER littora

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=6 \
  CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2).status == 200 else 1)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
