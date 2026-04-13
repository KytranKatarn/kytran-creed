FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

RUN groupadd -r appgroup && useradd -r -g appgroup -m appuser

WORKDIR /app
COPY pyproject.toml .
COPY kytran_creed/ kytran_creed/
RUN pip install --no-cache-dir .

RUN mkdir -p /data && chown appuser:appgroup /data
VOLUME ["/data"]

USER appuser

ENV KCR_HOST=0.0.0.0
ENV KCR_PORT=8086
ENV KCR_DATA_DIR=/data

EXPOSE 8086

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8086/health || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:8086", "--workers", "2", "--timeout", "120", "kytran_creed.app:create_app()"]
