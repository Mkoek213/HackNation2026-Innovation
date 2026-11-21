FROM python:3.13-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /uvx /bin/

WORKDIR /code

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

# Dependencies first, so code changes don't invalidate this layer
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project


FROM python:3.13-slim-bookworm

ARG CI_COMMIT_SHA=unknown
ARG CI_COMMIT_SHORT_SHA=unknown
ARG BUILD_TIME=unknown

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ="Europe/Warsaw" \
    PATH="/code/.venv/bin:$PATH" \
    PORT=8000 \
    CI_COMMIT_SHA=$CI_COMMIT_SHA \
    CI_COMMIT_SHORT_SHA=$CI_COMMIT_SHORT_SHA \
    BUILD_TIME=$BUILD_TIME

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata curl \
    && ln -fs /usr/share/zoneinfo/$TZ /etc/localtime \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 app

WORKDIR /code

COPY --from=builder /code/.venv /code/.venv

COPY --chown=app:app scripts ./scripts
COPY --chown=app:app config ./config
COPY --chown=app:app static ./static
COPY --chown=app:app alembic.ini ./alembic.ini
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app data ./data
COPY --chown=app:app app ./app

# Uploaded files live in the S3 bucket, not in the container.
RUN sed -i 's/$//' scripts/entrypoint.sh && chmod +x scripts/entrypoint.sh

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/healthcheck" > /dev/null || exit 1

ENTRYPOINT ["/code/scripts/entrypoint.sh"]
