# Output Style Definitions -- swag-mcp

Custom formatting for agent and tool responses.

## Current status

swag-mcp does not define custom output styles. The `TokenEfficientFormatter` handles all tool response formatting internally, producing compact output optimized for LLM token consumption.

## Token-efficient formatting

The formatter in `swag_mcp/utils/token_efficient_formatter.py` provides per-action formatting:

| Method | Action | Output style |
| --- | --- | --- |
| `format_list_result` | list | Compact table with config names and counts |
| `format_create_result` | create | Filename, backup status, health check result |
| `format_view_result` | view | Full config content with filename header |
| `format_edit_result` | edit | Success status and backup confirmation |
| `format_update_result` | update | Field change summary and health check |
| `format_remove_result` | remove | Removal confirmation and backup status |
| `format_logs_result` | logs | Log content with line count |
| `format_backup_result` | backups | List or cleanup summary |
| `format_health_check_result` | health_check | Status, HTTP code, response time |
| `format_error_result` | (any) | Action name and sanitized error |

See `docs/token-efficient-formatting.md` for the full formatting specification.
