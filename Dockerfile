# RaccBuddy Application Dockerfile
# Multi-stage build for smaller final image

FROM python:3.12-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Final stage
FROM python:3.12-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Create app directory
WORKDIR /app

# Copy application code
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY nudges/ ./nudges/
COPY skills/ ./skills/
COPY plugins/ ./plugins/
COPY docker-entrypoint.sh ./

# Make entrypoint executable
RUN chmod +x docker-entrypoint.sh

# Create a non-root user
RUN useradd -m -u 1000 raccbuddy && \
    chown -R raccbuddy:raccbuddy /app

USER raccbuddy

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health')" || exit 1

# Run migrations then start the application
ENTRYPOINT ["./docker-entrypoint.sh"]
