FROM python:3.11-slim AS builder

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Set working directory
WORKDIR /app

# Copy dependency files first for better caching
COPY pyproject.toml uv.lock README.md ./

# Install dependencies in a separate layer for better caching
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Copy source code only after dependencies are installed
COPY swag_mcp/ ./swag_mcp/
COPY templates/ ./templates/

FROM python:3.11-slim AS runtime

# Install system dependencies in one layer
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

# Create non-root user with fixed UID/GID
RUN groupadd -g 1000 swagmcp && \
    useradd -u 1000 -g swagmcp -m -s /bin/bash swagmcp

# Set working directory and ownership
WORKDIR /app
RUN chown swagmcp:swagmcp /app

# Copy virtual environment from builder
COPY --from=builder --chown=swagmcp:swagmcp /app/.venv /app/.venv

# Copy application code
COPY --from=builder --chown=swagmcp:swagmcp /app/swag_mcp/ ./swag_mcp/
COPY --from=builder --chown=swagmcp:swagmcp /app/templates/ ./templates/

# Create volume mount points and set ownership
RUN mkdir -p /proxy-confs /app/.swag-mcp /app/logs && \
    chown -R swagmcp:swagmcp /proxy-confs /app/.swag-mcp /app/logs

# Switch to non-root user early
USER swagmcp

# Environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    SWAG_MCP_SWAG_CONFIG_PATH=/proxy-confs \
    SWAG_MCP_TEMPLATE_PATH=/app/templates \
    SWAG_MCP_MCP_HOST=0.0.0.0 \
    SWAG_MCP_MCP_PORT=8000 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${SWAG_MCP_MCP_PORT:-8000}/health || exit 1

# Expose port
EXPOSE 8000

# Run the application
CMD ["python", "-m", "swag_mcp"]
