# Services and Ports

- Updated: `00:59:14 | 05/13/2026 EST`

| Service | Purpose | Host Bind | Host Port | Container Port | Notes |
| --- | --- | --- | --- | --- | --- |
| `swag-mcp` | MCP server for SWAG reverse proxy configuration management | `127.0.0.1` | `8012` | `8000` | Public route `https://swag.tootie.tv/mcp` proxies through SWAG to `swag-mcp:8000` on `jakenet`. |

Port allocation policy: use high, non-default host ports in the `49152-65535` range. Increment from `49152` for additional local services and record assignments here before deployment.
