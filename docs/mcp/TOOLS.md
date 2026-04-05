# MCP Tools Reference -- swag-mcp

## Design philosophy

swag-mcp uses a single unified tool (`swag`) with an `action` parameter to route operations, plus a companion `swag_help` tool. This 2-tool pattern reduces tool discovery overhead for MCP clients.

## Tool: `swag`

### Common parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `action` | SwagAction (enum) | required | Operation to perform |
| `config_name` | string (max 255) | `""` | Configuration filename (e.g., `jellyfin.subdomain.conf`) |
| `create_backup` | bool | `true` | Create backup before destructive operations |

### Action: `list`

List proxy configuration files with filtering, pagination, and sorting.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `list_filter` | `"all"` / `"active"` / `"samples"` | `"all"` | Filter configs by type |
| `offset` | int (>=0) | `0` | Pagination offset |
| `limit` | int (1-200) | `50` | Max results per page |
| `sort_by` | `"name"` / `"filename"` | `"name"` | Sort field |
| `sort_order` | `"asc"` / `"desc"` | `"asc"` | Sort direction |
| `query` | string | `""` | Case-insensitive filter string |

Response includes `items`, `total`, `limit`, `offset`, `has_more` for pagination.

### Action: `create`

Create a new nginx proxy configuration from the Jinja2 template.

| Parameter | Type | Default | Required | Description |
| --- | --- | --- | --- | --- |
| `config_name` | string | — | yes | Filename (e.g., `jellyfin.subdomain.conf`) |
| `server_name` | string (max 253) | — | yes | Domain (e.g., `media.example.com`) |
| `upstream_app` | string (max 100) | — | yes | Container name or IP |
| `upstream_port` | int (0-65535) | — | yes | Service port |
| `upstream_proto` | `"http"` / `"https"` | `"http"` | no | Upstream protocol |
| `auth_method` | string | `"authelia"` | no | Auth: none, basic, ldap, authelia, authentik, tinyauth |
| `enable_quic` | bool | `false` | no | Enable QUIC/HTTP3 |
| `mcp_upstream_app` | string (max 100) | `""` | no | Separate MCP container/IP (enables split routing) |
| `mcp_upstream_port` | int (0-65535) | `0` | no | MCP service port (inherits upstream_port if 0) |
| `mcp_upstream_proto` | `"http"` / `"https"` / null | `null` | no | MCP protocol (inherits upstream_proto if null) |

Split routing: when `mcp_upstream_app` is set, the config routes `/` to the main upstream and `/mcp` to the MCP upstream. All configs include MCP-compatible security headers regardless.

Post-create health check runs automatically against the `server_name`.

### Action: `view`

Read a configuration file's contents.

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `config_name` | string | yes | Configuration filename |

### Action: `edit`

Replace a configuration file's entire content.

| Parameter | Type | Default | Required | Description |
| --- | --- | --- | --- | --- |
| `config_name` | string | — | yes | Configuration filename |
| `new_content` | string | — | yes | Full replacement content |
| `create_backup` | bool | `true` | no | Create backup before edit |

### Action: `update`

Update a specific field in an existing configuration.

| Parameter | Type | Default | Required | Description |
| --- | --- | --- | --- | --- |
| `config_name` | string | — | yes | Configuration filename |
| `update_field` | `"port"` / `"upstream"` / `"app"` / `"add_mcp"` | — | yes | Field to update |
| `update_value` | string | — | yes | New value |
| `create_backup` | bool | `true` | no | Create backup before update |

Field behaviors:
- `port`: Updates `set $upstream_port` value
- `upstream`: Updates `set $upstream_app` and optionally port (format: `app:port`)
- `app`: Updates `set $upstream_app` value
- `add_mcp`: Adds MCP location block at the specified path (e.g., `/mcp`)

Post-update health check runs automatically if `server_name` can be extracted.

### Action: `remove`

Remove a configuration file.

| Parameter | Type | Default | Required | Description |
| --- | --- | --- | --- | --- |
| `config_name` | string | — | yes | Configuration filename |
| `create_backup` | bool | `true` | no | Create backup before removal |

### Action: `logs`

Retrieve SWAG log file contents.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `log_type` | `"nginx-access"` / `"nginx-error"` / `"fail2ban"` / `"letsencrypt"` / `"renewal"` | `"nginx-error"` | Log source |
| `lines` | int (1-1000) | `50` | Number of lines to retrieve |

Log paths map to files inside the SWAG container:
- `nginx-access` -> `/var/log/nginx/access.log`
- `nginx-error` -> `/var/log/nginx/error.log`
- `fail2ban` -> `/var/log/fail2ban/fail2ban.log`
- `letsencrypt` -> `/var/log/letsencrypt/letsencrypt.log`
- `renewal` -> `/var/log/letsencrypt/renewal.log`

### Action: `backups`

Manage configuration backup files.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `backup_action` | `"list"` / `"cleanup"` | `"list"` | Sub-action |
| `retention_days` | int (>=0) | `0` | Days to retain (cleanup only; 0 = use server default) |

### Action: `health_check`

HTTP health check against a proxied domain.

| Parameter | Type | Default | Required | Description |
| --- | --- | --- | --- | --- |
| `domain` | string (max 253) | — | yes | Domain to check (e.g., `media.example.com`) |
| `timeout` | int (1-300) | `30` | no | Request timeout in seconds |
| `follow_redirects` | bool | `true` | no | Follow HTTP redirects |

Returns success status, HTTP status code, and response time in milliseconds.

## Tool: `swag_help`

No parameters. Returns Markdown documentation listing all actions, their parameters, and examples.
