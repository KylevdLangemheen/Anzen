FROM python:3.14-slim

# Prevent Python from buffering logs
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# TODO: Install deps first (better caching)
COPY . .
RUN pip install --no-cache-dir /app

CMD ["python", "-m", "anzen"]
