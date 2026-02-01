FROM python:3.14-slim

# Prevent Python from buffering logs
ENV PYTHONUNBUFFERED=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY uv.lock pyproject.toml ./

RUN uv sync --frozen --no-install-project --no-cache

COPY . .
RUN uv sync --frozen --no-cache

CMD ["python", "-m", "anzen"]
