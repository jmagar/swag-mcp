ARG PYTHON_BASE_IMAGE=python:3.11-slim
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.10.10

FROM ${UV_IMAGE} AS uv-bin

FROM ${PYTHON_BASE_IMAGE} AS builder

# Install uv for fast dependency management
COPY --from=uv-bin /uv /uvx /usr/local/bin/

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

FROM ${PYTHON_BASE_IMAGE} AS runtime

# Install system dependencies in one layer
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl gosu && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

# Runtime only executes the prebuilt virtualenv; remove unused packaging tools
# inherited from the base image so image scans cover the actual runtime surface.
RUN rm -rf \
    /usr/local/bin/pip \
    /usr/local/bin/pip3 \
    /usr/local/bin/pip3.11 \
    /usr/local/lib/python3.11/site-packages/pip \
    /usr/local/lib/python3.11/site-packages/pip-*.dist-info \
    /usr/local/lib/python3.11/site-packages/setuptools \
    /usr/local/lib/python3.11/site-packages/setuptools-*.dist-info \
    /usr/local/lib/python3.11/site-packages/wheel \
    /usr/local/lib/python3.11/site-packages/wheel-*.dist-info

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
COPY --chown=root:root entrypoint.sh /usr/local/bin/swag-mcp-entrypoint
RUN chmod 755 /usr/local/bin/swag-mcp-entrypoint

# Create volume mount points and set ownership
RUN mkdir -p /proxy-confs /app/.swag-mcp /app/logs && \
    chown -R swagmcp:swagmcp /proxy-confs /app/.swag-mcp /app/logs

# Environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    SWAG_MCP_PROXY_CONFS_PATH=/proxy-confs \
    SWAG_MCP_TEMPLATE_PATH=/app/templates \
    SWAG_MCP_HOST=0.0.0.0 \
    SWAG_MCP_LOG_DIRECTORY=/app/.swag-mcp/logs \
    SWAG_MCP_REQUIRE_WRITABLE_LOG_DIRECTORY=true \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# The entrypoint starts as root only to align PUID/PGID and bind-mount ownership,
# then execs the application as the unprivileged runtime user.

# Health/readiness check. Port is always 8000 internally.
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import json, os, urllib.request; data=json.load(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)); assert data.get('status') == 'healthy'; assert os.access(os.environ['SWAG_MCP_LOG_DIRECTORY'], os.W_OK); assert os.path.isdir(os.environ['SWAG_MCP_PROXY_CONFS_PATH'])"

# Expose port
EXPOSE 8000

# Run the application
ENTRYPOINT ["swag-mcp-entrypoint"]
CMD ["python", "-m", "swag_mcp"]
