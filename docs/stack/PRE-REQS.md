# Prerequisites -- swag-mcp

Required tools and versions before developing or deploying.

## Runtime

| Tool | Version | Required for | Install |
| --- | --- | --- | --- |
| Python | 3.11+ | Server runtime | System package manager |
| uv | latest | Dependency management | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

## Development

| Tool | Version | Required for | Install |
| --- | --- | --- | --- |
| Docker | 24+ | Container builds | Docker official docs |
| Docker Compose | v2+ | Container orchestration | Bundled with Docker Desktop |
| just | latest | Task runner | `cargo install just` or system package |
| openssl | any | Token generation | System package manager |
| pre-commit | latest | Git hooks | `uv add --dev pre-commit` |

## Optional

| Tool | Version | Required for | Install |
| --- | --- | --- | --- |
| SSH client | any | Remote SWAG access | System package manager |
| curl | any | Health checks, testing | System package manager |
| jq | any | JSON output formatting | System package manager |

## SWAG server

For the MCP server to manage proxy configurations, a running SWAG instance is needed:

- **SWAG container** with the `proxy-confs` directory accessible
- **Filesystem access**: either local mount or SSH key-based access to the SWAG host
- **Log access** (optional): for the `logs` action, the SWAG log directory must be accessible

### Local access

Mount the SWAG proxy-confs directory:
```bash
SWAG_MCP_PROXY_CONFS_PATH=/mnt/appdata/swag/nginx/proxy-confs
```

### Remote access

Configure SSH key-based authentication to the SWAG host:
```bash
# Test SSH access
ssh swag-server ls /mnt/appdata/swag/nginx/proxy-confs/

# Set URI
SWAG_MCP_PROXY_CONFS_URI=admin@swag-server:/mnt/appdata/swag/nginx/proxy-confs
```

The SSH user must have read/write access to the proxy-confs directory.

## Network requirements

| Service | Port | Direction | Purpose |
| --- | --- | --- | --- |
| swag-mcp | 8000 | Inbound | MCP tool calls and health checks |
| SWAG host | 22 | Outbound | SSH/SFTP (remote mode only) |
| Proxied services | varies | Outbound | Health check verification |
