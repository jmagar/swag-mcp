# MCP Resources Reference

## Overview

swag-mcp exposes four MCP resources for configuration discovery and real-time monitoring.

## Static resources

### `swag://`

Active SWAG proxy configurations listed as a DirectoryResource.

- **URI**: `swag://`
- **Name**: Active SWAG Configurations
- **Type**: DirectoryResource
- **Pattern**: `*.conf` (excludes `.sample` files)
- **Path**: Value of `SWAG_MCP_PROXY_CONFS_PATH`

Returns a list of all `.conf` files in the proxy-confs directory.

## Streaming resources

### `swag://configs/live`

Real-time configuration change stream using a file watcher.

- **URI**: `swag://configs/live`
- **Name**: Config Change: {type}
- **MIME**: application/json
- **Content**: JSON with `config_name`, `type` (created/modified/deleted), `message`

Watches the proxy-confs directory for filesystem changes and emits events when configurations are created, modified, or deleted.

### `swag://health/stream`

Health status stream for monitored services.

- **URI**: `swag://health/stream/{count}`
- **Name**: Health Monitor ({n} services)
- **MIME**: text/plain
- **Interval**: 60 seconds
- **Limit**: First 5 active configurations

Periodically checks health of active proxy configurations and streams status updates.

### `swag://logs/stream`

Live SWAG nginx error log stream.

- **URI**: `swag://logs/stream/nginx-error`
- **Name**: SWAG Nginx Error Logs
- **MIME**: text/plain
- **Duration**: 5 minutes (300 seconds)

Streams nginx error log entries in real-time using the log streamer utility.
