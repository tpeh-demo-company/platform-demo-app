# Multi-stage Dockerfile for the platform demo application
# Stage 1: Builder - installs dependencies (Python minor version must match the runtime image)
FROM python:3.13-slim AS builder

WORKDIR /tmp
COPY requirements.txt .
RUN pip install --target /deps --no-cache-dir -r requirements.txt

# Stage 2: Runtime (distroless: no shell, no package manager, runs as nonroot)
FROM gcr.io/distroless/python3-debian13:nonroot

# Set metadata
LABEL maintainer="Platform Engineering Team"
LABEL description="Platform demo application for Chapter 5: Evaluate User Experience"

WORKDIR /app

# Copy dependencies from builder
COPY --from=builder /deps /deps

# Copy application code
COPY app.py instrumentation.py /app/

# Set environment
ENV PYTHONPATH=/deps
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python3", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:5000/health').read()"]

# Expose port
EXPOSE 5000

# Run application (the image entrypoint is python3)
CMD ["app.py"]
