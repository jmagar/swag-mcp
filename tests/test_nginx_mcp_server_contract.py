from pathlib import Path

MCP_SERVER_CONF = Path("config/nginx/mcp-server.conf")


def _mcp_server_conf_text() -> str:
    return MCP_SERVER_CONF.read_text(encoding="utf-8")


def test_mcp_server_routes_fastmcp_path_scoped_discovery_endpoints() -> None:
    text = _mcp_server_conf_text()

    expected_locations = [
        "location = /.well-known/oauth-authorization-server/mcp",
        "location = /.well-known/oauth-protected-resource/mcp",
    ]

    for location in expected_locations:
        assert location in text


def test_root_protected_resource_metadata_rewrites_to_fastmcp_resource_path() -> None:
    text = _mcp_server_conf_text()

    assert (
        "rewrite ^/.well-known/oauth-protected-resource$ "
        "/.well-known/oauth-protected-resource/mcp break;"
    ) in text


def test_reversed_protected_resource_probe_rewrites_to_fastmcp_resource_path() -> None:
    text = _mcp_server_conf_text()

    assert "location = /mcp/.well-known/oauth-protected-resource" in text
    assert (
        "rewrite ^/mcp/.well-known/oauth-protected-resource$ "
        "/.well-known/oauth-protected-resource/mcp break;"
    ) in text


def test_openid_discovery_probes_rewrite_to_authorization_server_metadata() -> None:
    text = _mcp_server_conf_text()

    expected_rewrites = [
        (
            "rewrite ^/.well-known/openid-configuration$ "
            "/.well-known/oauth-authorization-server break;"
        ),
        (
            "rewrite ^/.well-known/openid-configuration/mcp$ "
            "/.well-known/oauth-authorization-server break;"
        ),
        (
            "rewrite ^/mcp/.well-known/openid-configuration$ "
            "/.well-known/oauth-authorization-server break;"
        ),
    ]

    for rewrite in expected_rewrites:
        assert rewrite in text


def test_path_prefixed_oauth_endpoints_rewrite_to_fastmcp_root_routes() -> None:
    text = _mcp_server_conf_text()

    expected_rewrites = [
        "rewrite ^/mcp/register$ /register break;",
        "rewrite ^/mcp/authorize$ /authorize break;",
        "rewrite ^/mcp/token$ /token break;",
        "rewrite ^/mcp/revoke$ /revoke break;",
        "rewrite ^/mcp(/auth/.*)$ $1 break;",
        "rewrite ^/mcp/consent$ /consent break;",
    ]

    for rewrite in expected_rewrites:
        assert rewrite in text


def test_health_location_does_not_duplicate_proxy_timeout_directives() -> None:
    text = _mcp_server_conf_text()

    health_location = text.split("location = /health {", maxsplit=1)[1].split("}", maxsplit=1)[0]

    assert "include /config/nginx/proxy.conf;" not in health_location
    assert "proxy_connect_timeout 5s;" in health_location
