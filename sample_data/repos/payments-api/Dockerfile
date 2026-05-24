FROM python:3.11-slim AS build

ENV POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry==1.8.4

WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations

# ---- runtime ----
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash --uid 10001 svc

COPY --from=build /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=build /usr/local/bin /usr/local/bin
COPY --from=build /app /app

WORKDIR /app
USER svc:svc

EXPOSE 8080
ENV PYTHONUNBUFFERED=1
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s \
    CMD curl -fsSL http://localhost:8080/healthz || exit 1

CMD ["uvicorn", "payments_api.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
