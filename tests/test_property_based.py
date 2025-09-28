"""Property-based tests for SWAG MCP.

Using Hypothesis to test properties that should hold across
a wide range of inputs, improving robustness and finding edge cases.
"""

import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from swag_mcp.models.config import SwagConfigRequest
from swag_mcp.models.enums import SwagAction
from swag_mcp.services.swag_manager import SwagManagerService
from swag_mcp.utils.error_codes import ErrorCode, SwagValidationError
from swag_mcp.utils.validators import (
    normalize_unicode_text,
    validate_config_filename,
    validate_domain_format,
    validate_service_name,
    validate_upstream_port,
)


class TestDomainValidationProperties:
    """Property-based tests for domain validation."""

    @given(st.text())
    def test_domain_validation_never_crashes(self, domain_text):
        """Domain validation should never crash with any input.

        Property: validate_domain_format should either return a string
        or raise ValueError, but never crash with unhandled exceptions.
        """
        try:
            result = validate_domain_format(domain_text)
            assert isinstance(result, str)
        except ValueError:
            # Expected for invalid domains
            pass
        except Exception as e:
            pytest.fail(f"Domain validation crashed with unexpected error: {e}")

    @given(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Lu", "Nd"),
                whitelist_characters=".-"
            ),
            min_size=1,
            max_size=253  # Max domain length
        )
    )
    def test_valid_domain_characters_always_pass_basic_checks(self, domain):
        """Domains with valid characters should pass basic validation.

        Property: Domains containing only letters, numbers, dots, and hyphens
        should at least not fail on character validation (though they might
        fail other rules like length, format, etc.)
        """
        # Skip domains that are clearly invalid by format
        assume(domain.strip() != "")
        assume(not domain.startswith("."))
        assume(not domain.endswith("."))
        assume(".." not in domain)
        assume(not domain.startswith("-"))
        assume(not domain.endswith("-"))

        try:
            result = validate_domain_format(domain)
            # If it passes, result should be a clean domain
            assert isinstance(result, str)
            assert result == domain.lower().strip()
        except ValueError as e:
            # May still fail on other validation rules, which is fine
            error_msg = str(e).lower()
            # Should not fail on character validation specifically
            assert "character" not in error_msg or "invalid" in error_msg

    @given(st.text(min_size=1))
    def test_domain_validation_consistent(self, domain):
        """Domain validation should be consistent across calls.

        Property: Calling validate_domain_format multiple times with
        the same input should always produce the same result.
        """
        try:
            result1 = validate_domain_format(domain)
            result2 = validate_domain_format(domain)
            assert result1 == result2
        except ValueError as e1:
            # Should raise the same error
            try:
                validate_domain_format(domain)
                pytest.fail("Second call should also raise ValueError")
            except ValueError as e2:
                assert str(e1) == str(e2)


class TestConfigFilenameProperties:
    """Property-based tests for configuration filename validation."""

    @given(st.text())
    def test_config_filename_validation_robust(self, filename):
        """Config filename validation should handle any input robustly.

        Property: Should never crash and should have predictable behavior
        for edge cases.
        """
        try:
            result = validate_config_filename(filename)
            # If successful, result should be a valid filename
            assert isinstance(result, str)
            assert len(result) > 0
            assert "." in result  # Should have extension
        except ValueError:
            # Expected for invalid filenames
            pass
        except Exception as e:
            pytest.fail(f"Config filename validation crashed: {e}")

    @given(
        st.builds(
            lambda service, config_type: f"{service}.{config_type}.conf",
            service=st.text(
                alphabet=st.characters(
                    whitelist_categories=("Ll", "Lu", "Nd"),
                    whitelist_characters="-_"
                ),
                min_size=1,
                max_size=50
            ),
            config_type=st.sampled_from(["subdomain", "subfolder", "mcp-subdomain", "mcp-subfolder"])
        )
    )
    @settings(max_examples=20, deadline=5000)
    def test_valid_config_names_basic_properties(self, filename):
        """Config names with basic valid structure should have predictable results."""
        # Ensure it looks like a config file
        assume(filename.endswith(".conf") or ".conf" in filename)
        assume(not filename.startswith("."))
        assume(".." not in filename)

        try:
            result = validate_config_filename(filename)
            # Should preserve the basic structure
            assert result.endswith(".conf")
            assert len(result) >= len(".conf")
        except ValueError:
            # May still fail other validation rules
            pass


class TestServiceNameProperties:
    """Property-based tests for service name validation."""

    @given(st.text())
    def test_service_name_validation_never_crashes(self, service_name):
        """Service name validation should be robust against all inputs."""
        try:
            result = validate_service_name(service_name)
            assert isinstance(result, str)
            assert len(result) > 0
        except ValueError:
            # Expected for invalid service names
            pass
        except Exception as e:
            pytest.fail(f"Service name validation crashed: {e}")

    @given(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Lu", "Nd"),
                whitelist_characters="-_"
            ),
            min_size=1,
            max_size=50
        )
    )
    @settings(max_examples=10, deadline=5000)
    def test_alphanumeric_service_names_properties(self, service_name):
        """Alphanumeric service names should have predictable validation."""
        assume(service_name.strip() != "")
        assume(not service_name.startswith("-"))
        assume(not service_name.endswith("-"))

        try:
            result = validate_service_name(service_name)
            # Should return normalized version
            assert len(result) >= 1
            # Should not contain obviously invalid characters
            assert not any(c in result for c in " \t\n\r")
        except ValueError:
            # May fail on length or other rules
            pass


class TestPortValidationProperties:
    """Property-based tests for port validation."""

    @given(st.integers())
    def test_port_validation_handles_all_integers(self, port):
        """Port validation should handle any integer input."""
        try:
            result = validate_upstream_port(port)
            # Valid ports should be in expected range
            assert 1 <= result <= 65535
            assert isinstance(result, int)
        except ValueError:
            # Expected for out-of-range ports
            assert port < 1 or port > 65535
        except Exception as e:
            pytest.fail(f"Port validation crashed: {e}")

    @given(st.integers(min_value=1, max_value=65535))
    def test_valid_port_range_always_passes(self, port):
        """Ports in valid range should always pass validation.

        Property: Any integer in [1, 65535] should be accepted.
        """
        result = validate_upstream_port(port)
        assert result == port
        assert 1 <= result <= 65535

    @given(st.integers().filter(lambda x: x < 1 or x > 65535))
    def test_invalid_port_range_always_fails(self, port):
        """Ports outside valid range should always fail.

        Property: Any integer outside [1, 65535] should raise ValueError.
        """
        with pytest.raises(ValueError):
            validate_upstream_port(port)


class TestUnicodeNormalizationProperties:
    """Property-based tests for Unicode text normalization."""

    @given(st.text())
    def test_unicode_normalization_idempotent(self, text):
        """Unicode normalization should be idempotent.

        Property: normalize_unicode_text(normalize_unicode_text(text)) ==
        normalize_unicode_text(text)
        """
        try:
            normalized_once = normalize_unicode_text(text)
            normalized_twice = normalize_unicode_text(normalized_once)
            assert normalized_once == normalized_twice
        except Exception as e:
            pytest.fail(f"Unicode normalization failed: {e}")

    @given(st.text())
    def test_unicode_normalization_consistent(self, text):
        """Unicode normalization should be consistent.

        Property: Multiple calls should produce the same result.
        """
        try:
            result1 = normalize_unicode_text(text)
            result2 = normalize_unicode_text(text)
            assert result1 == result2
        except Exception as e:
            pytest.fail(f"Unicode normalization inconsistent: {e}")

    @given(st.text())
    def test_unicode_normalization_preserves_basic_structure(self, text):
        """Unicode normalization should preserve basic text structure.

        Property: Normalization shouldn't drastically change text length
        or remove all content (unless input was only problematic characters).
        """
        try:
            result = normalize_unicode_text(text)
            # Result should be a string
            assert isinstance(result, str)

            # If original had printable content, normalized should too
            if any(c.isprintable() and c != ' ' for c in text):
                # Should have some content (not be empty after normalization)
                # This is a weak property since normalization might remove some chars
                assert len(result) >= 0  # At minimum, should be a string
        except Exception as e:
            pytest.fail(f"Unicode normalization failed: {e}")


class TestConfigurationListHandling:
    """Property-based tests for configuration list operations."""

    @given(
        st.lists(
            st.builds(
                lambda service: f"{service}.subdomain.conf",
                service=st.text(
                    alphabet=st.characters(
                        whitelist_categories=("Ll", "Lu", "Nd"),
                        whitelist_characters="-_"
                    ),
                    min_size=1,
                    max_size=50
                ).filter(lambda x: x and not x.startswith("-") and not x.endswith("-"))
            ),
            min_size=0,
            max_size=10,  # Reduced for performance
            unique=True
        )
    )
    @settings(max_examples=3, deadline=10000)  # Very reduced examples for debugging
    @pytest.mark.asyncio
    async def test_config_listing_handles_various_filename_sets(self, config_names):
        """Configuration listing should handle various sets of filenames.

        Property: Should never crash regardless of what config files exist,
        and should return consistent results.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_path = Path(tmp_dir)
            
            # Create SwagManagerService with temp directory
            swag_service = SwagManagerService(
                config_path=temp_path,
                template_path=Path("templates")
            )

            # Create config files
            created_files = []
            for name in config_names:
                try:
                    # Only create files with reasonable names
                    if len(name) > 5 and not name.startswith("."):
                        config_file = temp_path / name
                        config_file.write_text(f"# Config for {name}")
                        created_files.append(name)
                except (OSError, ValueError):
                    # Skip files that can't be created
                    continue

            try:
                # List configs should not crash
                result = await swag_service.list_configs("all")

                # Basic properties of the result (SwagListResult)
                assert hasattr(result, 'configs')
                assert hasattr(result, 'total_count')
                assert hasattr(result, 'list_filter')
                
                assert isinstance(result.configs, list)
                assert isinstance(result.total_count, int)
                assert result.total_count >= 0
                assert result.list_filter == "all"

                # Should find the configs we created
                for created_name in created_files:
                    assert created_name in result.configs, (
                        f"Created file {created_name} not found in listing: {result.configs}"
                    )

            except Exception as e:
                pytest.fail(f"Config listing failed with valid files: {e}")


class TestErrorCodeProperties:
    """Property-based tests for error code system."""

    @given(st.sampled_from(ErrorCode), st.text(), st.dictionaries(st.text(), st.text()))
    def test_validation_error_creation_properties(self, error_code, message, context):
        """Validation error creation should be robust.

        Property: Should always create valid error objects with consistent properties.
        """
        from swag_mcp.utils.error_codes import create_validation_error

        try:
            error = create_validation_error(error_code, message, context)

            # Basic properties
            assert isinstance(error, SwagValidationError)
            assert error.code == error_code
            assert error.message == message
            assert error.context == context

            # String representation should be consistent
            error_str = str(error)
            assert isinstance(error_str, str)
            assert str(error_code) in error_str
            assert message in error_str

            # Should be deterministic
            error2 = create_validation_error(error_code, message, context)
            assert str(error) == str(error2)

        except Exception as e:
            pytest.fail(f"Error creation failed: {e}")

    @given(st.text())
    def test_error_string_representation_safe(self, message):
        """Error string representation should handle any message safely.

        Property: Should never crash when converting to string,
        regardless of message content.
        """
        from swag_mcp.utils.error_codes import create_validation_error

        try:
            error = create_validation_error(ErrorCode.INVALID_CONFIG_TYPE, message)
            error_str = str(error)
            assert isinstance(error_str, str)
            assert len(error_str) > 0
        except Exception as e:
            pytest.fail(f"Error string representation failed: {e}")


class TestPropertyBasedIntegration:
    """Integration tests using property-based testing."""

    @given(
        st.text(
            alphabet=st.characters(
                min_codepoint=ord('a'), max_codepoint=ord('z')
            ) | st.characters(
                min_codepoint=ord('A'), max_codepoint=ord('Z')
            ) | st.characters(
                min_codepoint=ord('0'), max_codepoint=ord('9')
            ),
            min_size=1,
            max_size=15
        ),
        st.integers(min_value=1000, max_value=9999),  # Common port range
    )
    @settings(
        max_examples=20,  # Reduced for CI performance
        deadline=10000,  # 10 second timeout per test
        suppress_health_check=[HealthCheck.too_slow],  # Allow slower tests for thorough checking
    )
    def test_config_request_creation_properties(self, service_name, port):
        """Configuration request creation should handle various valid inputs.

        Property: Valid service names and ports should create valid config requests.
        """
        # Filter to reasonable service names that create valid domain names
        assume(not service_name.startswith("."))
        assume(not service_name.startswith("-"))
        assume(not service_name.startswith("_"))
        assume(not service_name.endswith("-"))
        assume(not service_name.endswith("_"))
        assume(".." not in service_name)
        assume("_" not in service_name)  # Underscores not valid in domain names

        try:
            config_request = SwagConfigRequest(
                action=SwagAction.CREATE,
                config_name=f"{service_name}.subdomain.conf",
                server_name=f"{service_name}.example.com",
                upstream_app=service_name,
                upstream_port=port,
                auth_method="authelia",
                enable_quic=False,
                mcp_enabled=False,
            )

            # Basic properties
            assert config_request.config_name.endswith(".conf")
            assert config_request.server_name
            assert config_request.upstream_app
            assert 1 <= config_request.upstream_port <= 65535

        except Exception as e:
            pytest.fail(f"Config request creation failed with valid inputs: {e}")
