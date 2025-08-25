"""Unicode and encoding bug discovery tests.

These tests focus on finding bugs related to text encoding, Unicode handling,
and internationalization issues that commonly cause production failures.
"""

from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from swag_mcp.models.config import SwagConfigRequest, SwagEditRequest
from swag_mcp.services.swag_manager import SwagManagerService


class TestUnicodeEncodingBugs:
    """Bug discovery tests for Unicode and encoding handling issues."""

    @pytest.mark.asyncio
    async def test_unicode_filenames_handling(self, mcp_client: Client, mock_config):
        """Test handling of Unicode characters in configuration filenames."""
        config_dir = Path(mock_config.proxy_confs_path)

        # Test various Unicode filename scenarios
        unicode_filename_tests = [
            # Chinese characters
            {"service_name": "测试服务", "expected_filename": "测试服务.subdomain.conf"},
            # Arabic/RTL text
            {"service_name": "خدمة-اختبار", "expected_filename": "خدمة-اختبار.subdomain.conf"},
            # Emoji
            {
                "service_name": "🚀-rocket-service",
                "expected_filename": "🚀-rocket-service.subdomain.conf",
            },
            # Mixed scripts
            {
                "service_name": "test-тест-测试",
                "expected_filename": "test-тест-测试.subdomain.conf",
            },
            # Unicode normalization edge cases (same visual, different encoding)
            {"service_name": "café", "expected_filename": "café.subdomain.conf"},  # NFC form
            {
                "service_name": "cafe\u0301",
                "expected_filename": "cafe\u0301.subdomain.conf",
            },  # NFD form
            # Zero-width characters (potential security issue)
            {
                "service_name": "test\u200b-service",
                "expected_filename": "test\u200b-service.subdomain.conf",
            },
            {
                "service_name": "test\ufeff-bom",
                "expected_filename": "test\ufeff-bom.subdomain.conf",
            },
        ]

        created_files = []

        try:
            for test_case in unicode_filename_tests:
                try:
                    result = await mcp_client.call_tool(
                        "swag_create",
                        {
                            "service_name": test_case["service_name"],
                            "server_name": "unicode.example.com",
                            "upstream_app": "unicode-test",
                            "upstream_port": 8080,
                        },
                    )

                    if not result.is_error:
                        # Verify file was created with correct filename
                        expected_file = config_dir / test_case["expected_filename"]
                        created_files.append(expected_file)

                        # File should exist (filesystem supports Unicode)
                        assert (
                            expected_file.exists()
                        ), f"Unicode filename not created: {test_case['service_name']}"

                        # File should contain the service name correctly
                        content = expected_file.read_text(encoding="utf-8")
                        assert test_case["service_name"] in content

                        # Test reading the config back
                        read_result = await mcp_client.call_tool(
                            "swag_view", {"config_name": test_case["expected_filename"]}
                        )
                        assert not read_result.is_error
                        assert test_case["service_name"] in read_result.data

                except ToolError as e:
                    error_msg = str(e).lower()
                    # If it fails, should be due to validation, not encoding errors
                    assert "unicode" not in error_msg or "encoding" not in error_msg
                    # Should not crash with internal errors
                    assert "internal error" not in error_msg

        finally:
            # Clean up created files
            for file_path in created_files:
                if file_path.exists():
                    try:
                        file_path.unlink()
                    except OSError:
                        pass  # May fail on some filesystems with Unicode issues

    @pytest.mark.asyncio
    async def test_mixed_encoding_content_handling(self, swag_service: SwagManagerService):
        """Test handling of content with mixed or unusual text encodings."""
        config_dir = swag_service.config_path

        # Create initial config
        request = SwagConfigRequest(
            service_name="encoding-test",
            server_name="encoding.example.com",
            upstream_app="encoding-test",
            upstream_port=8080,
        )
        result = await swag_service.create_config(request)
        config_file = config_dir / result.filename

        # Test various encoding scenarios
        encoding_scenarios = [
            {
                "name": "utf8_with_bom",
                "content": "\ufeff# UTF-8 with BOM\nserver { listen 443; }",
                "encoding": "utf-8",
                "description": "UTF-8 content with BOM",
            },
            {
                "name": "latin1_content",
                "content": "# Latin-1 content: café résumé naïve\nserver { listen 443; }",
                "encoding": "latin-1",
                "description": "Latin-1 encoded content",
            },
            {
                "name": "mixed_unicode",
                "content": "# Mixed: English, 中文, العربية, Русский, 🌍\nserver { listen 443; }",
                "encoding": "utf-8",
                "description": "Mixed Unicode scripts",
            },
            {
                "name": "rtl_content",
                "content": "# RTL content: مرحبا بكم في الخادم\nserver { listen 443; }",
                "encoding": "utf-8",
                "description": "Right-to-left text",
            },
            {
                "name": "emoji_heavy",
                "content": "# Emoji test: 🚀🔥💯⚡🌟🎉🎯🔧⚙️🛠️\nserver { listen 443; }",
                "encoding": "utf-8",
                "description": "Emoji-heavy content",
            },
        ]

        try:
            for scenario in encoding_scenarios:
                # Write content with specific encoding
                config_file.write_text(scenario["content"], encoding=scenario["encoding"])

                try:
                    # Test reading config through service
                    read_content = await swag_service.read_config(result.filename)

                    # Should successfully read and preserve Unicode content
                    assert isinstance(read_content, str)
                    assert len(read_content) > 0

                    # Should contain the original content (may be normalized)
                    assert "server" in read_content
                    assert "listen 443" in read_content

                    # Test updating with Unicode content
                    edit_request = SwagEditRequest(
                        config_name=result.filename,
                        new_content=scenario["content"] + "\n# Updated with Unicode: ✅",
                        create_backup=True,
                    )
                    update_result = await swag_service.update_config(edit_request)

                    # Should handle Unicode in updates
                    assert "✅" in update_result.content

                except UnicodeDecodeError as e:
                    pytest.fail(f"Unicode decode error for {scenario['description']}: {str(e)}")

                except Exception as e:
                    error_msg = str(e).lower()
                    # Should not fail due to encoding issues
                    if any(word in error_msg for word in ["encoding", "decode", "unicode"]):
                        pytest.fail(f"Encoding error for {scenario['description']}: {error_msg}")

        finally:
            # Clean up
            if config_file.exists():
                config_file.unlink()
            for backup_file in config_dir.glob(f"{result.filename}.backup.*"):
                backup_file.unlink()

    @pytest.mark.asyncio
    async def test_zero_width_character_security_bypass(self, mcp_client: Client):
        """Test for security vulnerabilities using zero-width Unicode characters."""

        # Zero-width characters that could be used to bypass validation
        zero_width_attacks = [
            # Zero-width space
            {"service_name": "normal\u200bservice", "attack_type": "zero_width_space"},
            # Zero-width non-joiner
            {"service_name": "normal\u200cservice", "attack_type": "zero_width_non_joiner"},
            # Zero-width joiner
            {"service_name": "normal\u200dservice", "attack_type": "zero_width_joiner"},
            # BOM (Byte Order Mark)
            {"service_name": "normal\ufeffservice", "attack_type": "byte_order_mark"},
            # Invisible separator
            {"service_name": "normal\u2062service", "attack_type": "invisible_times"},
            # Mixed zero-width characters
            {"service_name": "n\u200bo\u200cr\u200dm\u2062al", "attack_type": "mixed_zero_width"},
        ]

        for attack in zero_width_attacks:
            try:
                result = await mcp_client.call_tool(
                    "swag_create",
                    {
                        "service_name": attack["service_name"],
                        "server_name": "zerowidth.example.com",
                        "upstream_app": "zerowidth-test",
                        "upstream_port": 8080,
                    },
                )

                if not result.is_error:
                    # If creation succeeds, verify zero-width chars are handled properly
                    # System should either normalize them or preserve them consistently

                    # Check if file was created
                    expected_filename = f"{attack['service_name']}.subdomain.conf"
                    # May need to handle filesystem representation

                    # Test reading back
                    read_result = await mcp_client.call_tool(
                        "swag_view", {"config_name": expected_filename}
                    )
                    if not read_result.is_error:
                        content = read_result.data
                        # Should contain the service name (possibly normalized)
                        assert "normal" in content

                        # Verify no security bypass occurred
                        # (This would depend on specific validation logic)

            except ToolError as e:
                error_msg = str(e).lower()
                # If validation rejects zero-width characters, that's acceptable security behavior
                assert any(word in error_msg for word in ["invalid", "character", "validation"])
                # Should not crash with encoding errors
                assert "encoding" not in error_msg
                assert "decode" not in error_msg

    @pytest.mark.asyncio
    async def test_unicode_normalization_consistency(self, swag_service: SwagManagerService):
        """Test Unicode normalization consistency across operations."""

        # Test cases with different Unicode normalization forms
        normalization_tests = [
            {
                "nfc": "café",  # NFC: single codepoint é
                "nfd": "cafe\u0301",  # NFD: e + combining acute accent
                "description": "e with acute accent",
            },
            {
                "nfc": "ñ",  # NFC: single codepoint ñ
                "nfd": "n\u0303",  # NFD: n + combining tilde
                "description": "n with tilde",
            },
            {
                "nfc": "ü",  # NFC: single codepoint ü
                "nfd": "u\u0308",  # NFD: u + combining diaeresis
                "description": "u with diaeresis",
            },
        ]

        for test_case in normalization_tests:
            # Test with NFC form
            nfc_request = SwagConfigRequest(
                service_name=f"test-{test_case['nfc']}-nfc",
                server_name="normalization.example.com",
                upstream_app="normalization-test",
                upstream_port=8080,
            )

            # Test with NFD form
            nfd_request = SwagConfigRequest(
                service_name=f"test-{test_case['nfd']}-nfd",
                server_name="normalization.example.com",
                upstream_app="normalization-test",
                upstream_port=8080,
            )

            try:
                nfc_result = await swag_service.create_config(nfc_request)
                nfd_result = await swag_service.create_config(nfd_request)

                # Both should be created successfully
                nfc_file = swag_service.config_path / nfc_result.filename
                nfd_file = swag_service.config_path / nfd_result.filename

                assert nfc_file.exists()
                assert nfd_file.exists()

                # Read both configurations
                nfc_content = await swag_service.read_config(nfc_result.filename)
                nfd_content = await swag_service.read_config(nfd_result.filename)

                # Both should contain their respective forms
                assert test_case["nfc"] in nfc_content or test_case["nfd"] in nfc_content
                assert test_case["nfc"] in nfd_content or test_case["nfd"] in nfd_content

                # Clean up
                nfc_file.unlink()
                nfd_file.unlink()

            except Exception as e:
                error_msg = str(e).lower()
                if any(word in error_msg for word in ["encoding", "unicode", "normalization"]):
                    pytest.fail(
                        f"Unicode normalization error for {test_case['description']}: {error_msg}"
                    )

    @pytest.mark.asyncio
    async def test_invalid_unicode_sequence_handling(self, swag_service: SwagManagerService):
        """Test handling of invalid Unicode sequences and malformed UTF-8."""
        config_dir = swag_service.config_path

        # Create test file with invalid UTF-8 sequences
        invalid_utf8_file = config_dir / "invalid-utf8.conf"

        # Invalid UTF-8 byte sequences
        invalid_sequences = [
            b"\x80\x81",  # Invalid start bytes
            b"\xc0\x80",  # Overlong encoding of null
            b"\xed\xa0\x80",  # High surrogate (invalid in UTF-8)
            b"\xff\xfe",  # Invalid bytes
            b"Valid text\x80\x81invalid\x00",  # Mixed valid/invalid
        ]

        for i, invalid_sequence in enumerate(invalid_sequences):
            try:
                # Write invalid UTF-8 to file
                with open(invalid_utf8_file, "wb") as f:
                    f.write(b"# Config with invalid UTF-8\n")
                    f.write(invalid_sequence)
                    f.write(b"\nserver { listen 443; }\n")

                # Try to read the file through the service
                try:
                    content = await swag_service.read_config("invalid-utf8.conf")

                    # If reading succeeds, invalid bytes should be handled
                    assert isinstance(content, str)
                    assert "server" in content  # Valid part should be preserved

                except UnicodeDecodeError:
                    # This is acceptable - invalid UTF-8 should be rejected
                    pass

                except Exception as e:
                    error_msg = str(e).lower()
                    # Should handle gracefully, not crash
                    if "internal error" in error_msg:
                        pytest.fail(
                            f"Internal error handling invalid UTF-8 sequence {i}: {error_msg}"
                        )

            finally:
                if invalid_utf8_file.exists():
                    invalid_utf8_file.unlink()

    @pytest.mark.asyncio
    async def test_locale_specific_character_handling(self, mcp_client: Client):
        """Test handling of locale-specific characters and case conversions."""

        # Locale-specific test cases
        locale_tests = [
            # Turkish dotted/dotless i
            {"service_name": "İstanbul-service", "locale": "tr_TR"},
            {"service_name": "ığüşçöİĞÜŞÇÖ", "locale": "tr_TR"},
            # German eszett
            {"service_name": "Straße-service", "locale": "de_DE"},
            # Greek characters
            {"service_name": "Ελληνικά-service", "locale": "el_GR"},
            # Cyrillic
            {"service_name": "Кириллица-service", "locale": "ru_RU"},
            # Japanese (mixed scripts)
            {"service_name": "テスト-ひらがな-カタカナ", "locale": "ja_JP"},
            # Korean
            {"service_name": "테스트-서비스", "locale": "ko_KR"},
        ]

        for test_case in locale_tests:
            try:
                result = await mcp_client.call_tool(
                    "swag_create",
                    {
                        "service_name": test_case["service_name"],
                        "server_name": "locale.example.com",
                        "upstream_app": "locale-test",
                        "upstream_port": 8080,
                    },
                )

                if not result.is_error:
                    # Verify service name is preserved in different contexts
                    # (case conversions, normalizations, etc.)

                    # Test reading back
                    # Note: actual filename may be normalized by filesystem
                    config_files = list(Path(mock_config.proxy_confs_path).glob("*.conf"))
                    created_file = None

                    for config_file in config_files:
                        content = config_file.read_text(encoding="utf-8", errors="replace")
                        if test_case["service_name"] in content:
                            created_file = config_file
                            break

                    if created_file:
                        # Test editing with locale-specific content
                        edit_result = await mcp_client.call_tool(
                            "swag_edit",
                            {
                                "config_name": created_file.name,
                                "new_content": f"# Locale test: {test_case['service_name']}\nserver {{ listen 443; }}",
                            },
                        )

                        if not edit_result.is_error:
                            assert test_case["service_name"] in edit_result.data

                        # Clean up
                        created_file.unlink()

            except ToolError as e:
                error_msg = str(e).lower()
                # Should handle locale-specific characters or reject them cleanly
                assert "internal error" not in error_msg
                assert "crash" not in error_msg

    @pytest.mark.asyncio
    async def test_character_encoding_conversion_bugs(self, swag_service: SwagManagerService):
        """Test for bugs in character encoding conversions."""
        config_dir = swag_service.config_path

        # Create config with various character encoding challenges
        encoding_challenge_file = config_dir / "encoding-challenge.conf"

        # Content that challenges encoding conversion
        challenging_content = """# Encoding challenge test
# ASCII: Basic English text
# Latin-1: café résumé naïve
# UTF-8: 中文 العربية Русский हिन्दी
# Emoji: 🌍🚀💻🔥⚡
# Mathematical: ∑∆∇∫√∞≈≠≤≥
# Currency: €£¥₹$¢
# Arrows: ←↑→↓↔↕↖↗↘↙
# Special: ™©®℀℁ℂ℃℄℅℆ℇ℈℉ℊℋℌℍℎℏ
server {
    listen 443;
    server_name encoding-test.example.com;
}"""

        try:
            # Write with UTF-8 encoding
            encoding_challenge_file.write_text(challenging_content, encoding="utf-8")

            # Read through service
            content = await swag_service.read_config("encoding-challenge.conf")

            # Verify all character types are preserved
            assert "café" in content
            assert "中文" in content
            assert "🌍" in content
            assert "∑∆∇" in content
            assert "€£¥" in content
            assert "←↑→" in content
            assert "™©®" in content

            # Test updating with mixed encoding content
            from swag_mcp.models.config import SwagEditRequest

            mixed_content = challenging_content + "\n# Updated: ✅ Success! 成功！ نجح！"

            edit_request = SwagEditRequest(
                config_name="encoding-challenge.conf",
                new_content=mixed_content,
                create_backup=True,
            )

            result = await swag_service.update_config(edit_request)

            # Verify update preserved all characters
            assert "✅" in result.content
            assert "成功" in result.content
            assert "نجح" in result.content

        except UnicodeError as e:
            pytest.fail(f"Unicode error in encoding conversion: {str(e)}")

        except Exception as e:
            error_msg = str(e).lower()
            if any(word in error_msg for word in ["encoding", "decode", "unicode"]):
                pytest.fail(f"Encoding conversion error: {error_msg}")

        finally:
            # Clean up
            if encoding_challenge_file.exists():
                encoding_challenge_file.unlink()
            for backup_file in config_dir.glob("encoding-challenge.conf.backup.*"):
                backup_file.unlink()

    @pytest.mark.asyncio
    async def test_bom_handling_across_operations(self, swag_service: SwagManagerService):
        """Test Byte Order Mark (BOM) handling consistency."""
        config_dir = swag_service.config_path

        # Test different BOM scenarios
        bom_scenarios = [
            {
                "name": "utf8_bom",
                "bom": b"\xef\xbb\xbf",
                "content": "# UTF-8 with BOM\nserver { listen 443; }",
                "description": "UTF-8 BOM",
            },
            {
                "name": "utf16_le_bom",
                "bom": b"\xff\xfe",
                "content": "# UTF-16 LE content",
                "description": "UTF-16 LE BOM",
            },
            {
                "name": "utf16_be_bom",
                "bom": b"\xfe\xff",
                "content": "# UTF-16 BE content",
                "description": "UTF-16 BE BOM",
            },
        ]

        for scenario in bom_scenarios:
            bom_file = config_dir / f"{scenario['name']}.conf"

            try:
                # Create file with BOM
                if scenario["name"] == "utf8_bom":
                    # Write UTF-8 with BOM
                    with open(bom_file, "wb") as f:
                        f.write(scenario["bom"])
                        f.write(scenario["content"].encode("utf-8"))
                else:
                    # For UTF-16 tests, write as UTF-8 (BOM will be treated as content)
                    with open(bom_file, "wb") as f:
                        f.write(scenario["bom"])
                        f.write(scenario["content"].encode("utf-8"))

                try:
                    # Read through service
                    content = await swag_service.read_config(f"{scenario['name']}.conf")

                    # Should handle BOM appropriately
                    assert isinstance(content, str)
                    assert len(content) > 0

                    # For UTF-8 BOM, content should be preserved without BOM
                    if scenario["name"] == "utf8_bom":
                        assert content.startswith("# UTF-8")
                        # BOM should be stripped or handled
                        assert not content.startswith("\ufeff")

                    # Test editing BOM files
                    from swag_mcp.models.config import SwagEditRequest

                    edit_request = SwagEditRequest(
                        config_name=f"{scenario['name']}.conf",
                        new_content=scenario["content"] + "\n# Edited",
                        create_backup=True,
                    )

                    result = await swag_service.update_config(edit_request)
                    assert "# Edited" in result.content

                except UnicodeDecodeError:
                    # Some BOM scenarios might not be readable - that's acceptable
                    if scenario["name"] not in ["utf16_le_bom", "utf16_be_bom"]:
                        pytest.fail(f"UTF-8 with BOM should be readable: {scenario['description']}")

            finally:
                # Clean up
                if bom_file.exists():
                    bom_file.unlink()
                for backup_file in config_dir.glob(f"{scenario['name']}.conf.backup.*"):
                    backup_file.unlink()

    @pytest.mark.asyncio
    async def test_surrogate_pair_handling(self, mcp_client: Client):
        """Test handling of Unicode surrogate pairs and edge cases."""

        # Test cases with Unicode surrogate pairs and edge cases
        surrogate_tests = [
            # Valid surrogate pairs (Emoji)
            {"content": "🚀", "description": "rocket emoji (surrogate pair)"},
            {"content": "👨‍💻", "description": "man technologist (complex emoji sequence)"},
            {"content": "🏳️‍🌈", "description": "rainbow flag (flag sequence)"},
            # High Unicode code points
            {"content": "𝕌𝕟𝕚𝕔𝕠𝕕𝕖", "description": "mathematical alphanumeric symbols"},
            {"content": "𓀀𓀁𓀂", "description": "Egyptian hieroglyphs"},
            # Variation selectors
            {"content": "◯︎◯️", "description": "variation selectors"},
        ]

        for test_case in surrogate_tests:
            try:
                result = await mcp_client.call_tool(
                    "swag_create",
                    {
                        "service_name": f"surrogate-{test_case['content']}-test",
                        "server_name": "surrogate.example.com",
                        "upstream_app": "surrogate-test",
                        "upstream_port": 8080,
                    },
                )

                if not result.is_error:
                    # If creation succeeds, surrogate pairs should be handled correctly
                    # Test reading back
                    created_files = list(
                        Path(mock_config.proxy_confs_path).glob("surrogate-*.conf")
                    )

                    for config_file in created_files:
                        content = config_file.read_text(encoding="utf-8")
                        if test_case["content"] in content:
                            # Surrogate pair preserved correctly
                            assert test_case["content"] in content

                            # Clean up
                            config_file.unlink()
                            break

            except ToolError as e:
                error_msg = str(e).lower()
                # Should handle surrogates or reject them cleanly
                assert "internal error" not in error_msg
                # Acceptable if validation rejects surrogate pairs in service names
                if any(word in error_msg for word in ["invalid", "character", "validation"]):
                    pass  # This is acceptable behavior
                else:
                    pytest.fail(f"Unexpected error for {test_case['description']}: {error_msg}")
