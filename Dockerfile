FROM python:3.11-slim AS builder

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock README.md ./

# Copy source code for package build
COPY swag_mcp/ ./swag_mcp/

# Install dependencies
RUN uv sync --frozen --no-cache

FROM python:3.11-slim AS runtime

# Set working directory
WORKDIR /app

# Install curl for health checks
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security with specific UID to match host
RUN groupadd -g 1000 swagmcp && useradd -u 1000 -g swagmcp swagmcp

# Copy virtual environment from builder
COPY --from=builder --chown=swagmcp:swagmcp /app/.venv /app/.venv

# Copy application code
COPY --chown=swagmcp:swagmcp swag_mcp/ ./swag_mcp/
COPY --chown=swagmcp:swagmcp templates/ ./templates/

# Create volume mount points, config directories, and logs directory
RUN mkdir -p /proxy-confs /app/.swag-mcp /app/logs && \
    chown -R swagmcp:swagmcp /proxy-confs /app/.swag-mcp /app/logs

# Ensure virtual environment is activated
ENV PATH="/app/.venv/bin:$PATH"

# Set environment variables for containerized paths
ENV SWAG_MCP_SWAG_CONFIG_PATH=/proxy-confs
ENV SWAG_MCP_TEMPLATE_PATH=/app/templates
ENV SWAG_MCP_MCP_HOST=0.0.0.0
ENV SWAG_MCP_MCP_PORT=8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Switch to non-root user
USER swagmcp

# Expose MCP server port
EXPOSE 8000

# Run the application
CMD ["python", "-m", "swag_mcp"]
