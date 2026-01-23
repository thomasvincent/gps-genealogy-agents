# Multi-stage build for production
FROM python:3.13-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    librocksdb-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

# Copy only dependency files first (for layer caching)
WORKDIR /app
COPY pyproject.toml ./
COPY uv.lock* ./

# Install dependencies
RUN uv pip install --system -e ".[all]"

# Final stage
FROM python:3.13-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    librocksdb-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
WORKDIR /app
COPY . .

# Install the package itself
RUN pip install --no-cache-dir -e .

# Create non-root user
RUN useradd -m -u 1000 gpsagent && chown -R gpsagent:gpsagent /app
USER gpsagent

# Set environment to production
ENV ENVIRONMENT=production
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import gps_agents; print('healthy')" || exit 1

# Default command
CMD ["gps-agents", "--help"]
