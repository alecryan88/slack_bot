# Stage 1: Builder
# Uses the official uv image to install dependencies directly into /app/packages
# using --target, so they land flat on the filesystem (no venv) — required for Lambda.
FROM --platform=linux/amd64 ghcr.io/astral-sh/uv:python3.11-bookworm AS builder

WORKDIR /app

# Install dependencies first before copying app code.
# This layer is cached and only re-runs when pyproject.toml or uv.lock change.
COPY pyproject.toml uv.lock ./
RUN uv pip install --target /app/packages -r pyproject.toml

# Copy app code
COPY handler.py .
COPY listeners/ listeners/
COPY ai/ ai/


# Stage 2: Final Lambda image
# Starts fresh from the official Lambda base image and copies only the built
# app and packages from the builder stage — no uv, no build tools, no intermediate files.
FROM --platform=linux/amd64 public.ecr.aws/lambda/python:3.11

# Copy installed packages flat into task root so Lambda's Python can find them
COPY --from=builder /app/packages ${LAMBDA_TASK_ROOT}

# Copy app code
COPY --from=builder /app/handler.py ${LAMBDA_TASK_ROOT}
COPY --from=builder /app/listeners ${LAMBDA_TASK_ROOT}/listeners
COPY --from=builder /app/ai ${LAMBDA_TASK_ROOT}/ai

CMD ["handler.handler"]
