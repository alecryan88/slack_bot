# Stage 1: Install dependencies
FROM --platform=linux/amd64 ghcr.io/astral-sh/uv:python3.11-bookworm AS builder

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv pip install --target /app/packages -r pyproject.toml

COPY handler.py .
COPY listeners/ listeners/
COPY ai/ ai/


# Stage 2: Runtime
FROM --platform=linux/amd64 python:3.11-slim

WORKDIR /app

COPY --from=builder /app/packages /app/packages
COPY --from=builder /app/handler.py .
COPY --from=builder /app/listeners listeners/
COPY --from=builder /app/ai ai/

ENV PYTHONPATH=/app/packages

CMD ["python", "handler.py"]
