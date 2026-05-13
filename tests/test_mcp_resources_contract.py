"""Contract tests for MCP resources exposed by the FastMCP server."""

import json

import pytest
from fastmcp import Client

pytestmark = pytest.mark.asyncio


async def test_all_advertised_resources_are_readable(mcp_client: Client) -> None:
    """Every listed resource can be read without returning generator objects."""
    listed = await mcp_client.list_resources()
    resource_uris = {str(resource.uri) for resource in listed}

    expected_uris = {
        "swag://",
        "swag://configs/live",
        "swag://health/stream",
        "swag://logs/stream",
    }
    assert expected_uris <= resource_uris

    for resource_uri in expected_uris:
        result = await mcp_client.read_resource(resource_uri)
        assert result, f"{resource_uri} returned no content"
        assert all(hasattr(content, "text") for content in result)


async def test_static_swag_resource_lists_active_configs(mcp_client: Client) -> None:
    """The static swag:// resource returns JSON with active config filenames."""
    result = await mcp_client.read_resource("swag://")

    assert result
    payload = json.loads(result[0].text)
    assert "files" in payload
    assert isinstance(payload["files"], list)
