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
    local required="${2:-false}"
    local required_normalized="${required,,}"
    local is_required=false

    case "${required_normalized}" in
        true|1|yes) is_required=true ;;
    esac

    mkdir -p "${path}"
    if ! chown -R "${PUID}:${PGID}" "${path}" 2>/dev/null; then
        if [ "${is_required}" = "true" ]; then
            echo "Error: Could not set ownership for required directory ${path}" >&2
            exit 1
        fi
        echo "Warning: Could not set ownership for ${path}; continuing" >&2
    fi

    if ! gosu "${PUID}:${PGID}" test -w "${path}"; then
        if [ "${is_required}" = "true" ]; then
            echo "Error: Required directory ${path} is not writable by ${PUID}:${PGID}" >&2
            exit 1
        fi
        echo "Warning: ${path} is not writable by ${PUID}:${PGID}" >&2
    fi
}

prepare_ssh_directory() {
    local ssh_dir="/home/${APP_USER}/.ssh"

    mkdir -p "${ssh_dir}"
    chown "${PUID}:${PGID}" "${ssh_dir}" 2>/dev/null || true
    chmod 700 "${ssh_dir}" 2>/dev/null || true
}

if [ "$(id -u)" = "0" ]; then
    ensure_runtime_user

    export SWAG_MCP_LOG_DIRECTORY="${SWAG_MCP_LOG_DIRECTORY:-/app/.swag-mcp/logs}"
    require_log_directory="${SWAG_MCP_REQUIRE_WRITABLE_LOG_DIRECTORY:-true}"

    prepare_ssh_directory
    prepare_directory "/app/.swag-mcp" true
    prepare_directory "${SWAG_MCP_LOG_DIRECTORY}" "${require_log_directory}"
    prepare_directory "/app/logs" true
    prepare_directory "/home/${APP_USER}/.local/share/fastmcp" true
    prepare_directory "${SWAG_MCP_PROXY_CONFS_PATH:-/proxy-confs}" true

    exec gosu "${PUID}:${PGID}" "$@"
fi

exec "$@"
