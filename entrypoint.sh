#!/bin/bash
set -euo pipefail

APP_USER="swagmcp"
APP_GROUP="swagmcp"
PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

ensure_runtime_user() {
    if ! getent group "${APP_GROUP}" >/dev/null; then
        groupadd -g "${PGID}" "${APP_GROUP}"
    elif [ "$(getent group "${APP_GROUP}" | cut -d: -f3)" != "${PGID}" ]; then
        groupmod -g "${PGID}" "${APP_GROUP}"
    fi

    if ! id -u "${APP_USER}" >/dev/null 2>&1; then
        useradd -u "${PUID}" -g "${PGID}" -m -s /bin/bash "${APP_USER}"
    elif [ "$(id -u "${APP_USER}")" != "${PUID}" ]; then
        usermod -u "${PUID}" -g "${PGID}" "${APP_USER}"
    else
        usermod -g "${PGID}" "${APP_USER}"
    fi
}

prepare_directory() {
    local path="$1"

    mkdir -p "${path}"
    if ! chown -R "${PUID}:${PGID}" "${path}" 2>/dev/null; then
        echo "Warning: Could not set ownership for ${path}; continuing" >&2
    fi

    if ! gosu "${PUID}:${PGID}" test -w "${path}"; then
        echo "Warning: ${path} is not writable by ${PUID}:${PGID}" >&2
    fi
}

if [ "$(id -u)" = "0" ]; then
    ensure_runtime_user

    export SWAG_MCP_LOG_DIRECTORY="${SWAG_MCP_LOG_DIRECTORY:-/app/.swag-mcp/logs}"

    prepare_directory "/app/.swag-mcp"
    prepare_directory "${SWAG_MCP_LOG_DIRECTORY}"
    prepare_directory "/app/logs"
    prepare_directory "/home/${APP_USER}/.local/share/fastmcp"
    prepare_directory "/proxy-confs"

    exec gosu "${PUID}:${PGID}" "$@"
fi

exec "$@"
