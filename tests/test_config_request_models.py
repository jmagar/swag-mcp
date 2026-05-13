"""Focused tests for SWAG request model boundaries."""

import pytest
from swag_mcp.models.config import SwagConfigRequest
from swag_mcp.models.enums import SwagAction


def test_service_request_model_accepts_legacy_action_without_exposing_it() -> None:
    """Service command models drop transport-level action after validation."""
    request = SwagConfigRequest(
        action=SwagAction.CREATE,
        config_name="app.subdomain.conf",
        server_name="app.example.com",
        upstream_app="app",
        upstream_port=8080,
    )

    assert not hasattr(request, "action")
    assert "action" not in request.model_dump()
    assert "action" not in SwagConfigRequest.model_json_schema()["properties"]


def test_empty_config_name_has_clear_error_message() -> None:
    """Empty config names should not be reported as path traversal."""
    with pytest.raises(ValueError, match="Config name cannot be empty"):
        SwagConfigRequest(
            config_name=" ",
            server_name="app.example.com",
            upstream_app="app",
            upstream_port=8080,
        )
