from pathlib import Path

SCRIPT = Path("tests/mcporter/test-tools.sh")


def _script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_mcporter_script_covers_every_swag_action() -> None:
    text = _script_text()

    expected_suites = [
        "suite_tool_contract",
        "suite_lifecycle",
        "suite_logs",
        "suite_backups",
        "suite_health",
        "suite_resources",
    ]
    for suite in expected_suites:
        assert f"{suite}()" in text

    expected_actions = [
        '"action":"list"',
        '"action":"create"',
        '"action":"view"',
        '"action":"update"',
        '"action":"edit"',
        '"action":"remove"',
        '"action":"logs"',
        '"action":"backups"',
        '"action":"health_check"',
    ]
    for action in expected_actions:
        assert action in text

    for update_field in ["port", "upstream", "app", "add_mcp"]:
        assert f'"update_field":"{update_field}"' in text


def test_mcporter_script_validates_structured_results() -> None:
    text = _script_text()

    expected_helpers = [
        "assert_tool_success()",
        "assert_json_expr()",
        "assert_file_contains()",
        "assert_file_not_exists()",
        "extract_tool_json()",
    ]
    for helper in expected_helpers:
        assert helper in text

    expected_assertions = [
        'json_assert_equals "swag: list all exact filter"',
        'json_assert_equals "${label}" "${json_payload}" "filename"',
        'json_assert_truthy "${label}: content present"',
        'json_assert_truthy "${label}" "${json_payload}" "backup_created"',
        'json_assert_equals "${label}: domain"',
        'json_assert_not_none "${label}: total"',
    ]
    for assertion in expected_assertions:
        assert assertion in text


def test_mcporter_script_covers_mcp_resources() -> None:
    text = _script_text()

    assert "mcporter_list_resources()" in text
    assert "mcporter_read_resource()" in text

    expected_resources = [
        "swag://",
        "swag://configs/live",
        "swag://health/stream",
        "swag://logs/stream",
    ]
    for resource_uri in expected_resources:
        assert resource_uri in text


def test_mcporter_script_uses_named_json_assertions_without_eval() -> None:
    text = _script_text()

    assert "eval(" not in text
    for helper in [
        "json_assert_equals()",
        "json_assert_truthy()",
        "json_assert_list_contains()",
        "json_assert_type()",
    ]:
        assert helper in text


def test_mcporter_script_tracks_blocked_capability_gaps() -> None:
    text = _script_text()

    assert "BLOCK_COUNT=0" in text
    assert "block_test()" in text
    assert "print_blockers()" in text
    assert "preflight_write_capability()" in text
    assert "WRITE_CAPABILITY=" in text
    assert "DISK_VERIFY_CAPABILITY=" in text


def test_mcporter_script_has_negative_resource_and_cleanup_assertions() -> None:
    text = _script_text()

    for suite in [
        "suite_negative_contracts",
        "assert_tool_error",
        "assert_resource_text_json_field",
        "assert_backups_for_test_config",
        "cleanup_test_backups",
    ]:
        assert suite in text

    for payload in [
        '"action":"not_a_real_action"',
        '"action":"create"',
        '"list_filter":"invalid"',
        '"update_field":"invalid"',
        "../bad.subdomain.conf",
    ]:
        assert payload in text

    for resource_assertion in [
        "watcher_snapshot",
        "health_snapshot",
        "SWAG nginx-error Log Stream",
    ]:
        assert resource_assertion in text
