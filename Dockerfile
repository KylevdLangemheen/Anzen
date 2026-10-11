FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim

# Prevent Python from buffering logs
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY uv.lock pyproject.toml ./

RUN uv sync --frozen --no-install-project --no-cache

COPY . .
RUN uv sync --frozen --no-cache

CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && uv run --no-sync python -m anzen"]
