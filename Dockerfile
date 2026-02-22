FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim

RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*

# Prevent Python from buffering logs
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY uv.lock pyproject.toml ./

RUN uv sync --frozen --no-install-project --no-cache

COPY . .
RUN uv sync --frozen --no-cache

CMD ["uv", "run", "python", "-m", "anzen"]
