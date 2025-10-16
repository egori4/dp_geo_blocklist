FROM python:3.11-slim

# Create non-root user for security
RUN groupadd -r geoip && useradd -r -g geoip geoip

# Set working directory
WORKDIR /app

# Install system dependencies if needed (minimal approach)
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY src/ ./src/

# Create data directory for volume mount
RUN mkdir -p /app/data && chown -R geoip:geoip /app

# Switch to non-root user
USER geoip

# Default command - runs the main application
CMD ["python", "-m", "src.cli.main"]

# Labels for container metadata
LABEL maintainer="GeoIP Custom IP Blocker"
LABEL version="1.0.0"
LABEL description="Containerized Python application for GeoIP-based IP range synchronization"

# Expose volume for persistent data
VOLUME ["/app/data"]