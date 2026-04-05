# Scheduled Tasks -- swag-mcp

Automated recurring agent execution on a cron schedule.

## Current status

swag-mcp does not define any scheduled tasks. The backup cleanup operation runs at server startup (not on a schedule).

## Startup cleanup

On server start, `cleanup_old_backups()` removes backup files older than `SWAG_MCP_BACKUP_RETENTION_DAYS`. This is a one-time operation, not a recurring schedule.

## When to add schedules

Consider adding scheduled tasks for:
- Periodic health checks of all proxied domains
- Regular backup cleanup (if startup-only is insufficient)
- Certificate renewal monitoring
- Configuration drift detection (comparing live configs against expected state)
