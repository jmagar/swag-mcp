"""Validation utilities for SWAG MCP server."""

import logging
import re
import unicodedata
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def validate_domain_format(domain: str) -> str:
    """Validate domain name format.

    Args:
        domain: Domain name to validate

    Returns:
        Lowercase domain name if valid

    Raises:
        ValueError: If domain format is invalid

    """
    if not domain:
        raise ValueError("Domain name cannot be empty")

    if len(domain) > 253:
        raise ValueError("Domain name is too long (maximum 253 characters)")

    if ".." in domain:
        raise ValueError("Domain name cannot contain consecutive dots")

    if domain.startswith(".") or domain.endswith("."):
        raise ValueError("Domain name cannot start or end with a dot")

    # Split domain into parts for more specific validation
    parts = domain.split(".")

    if len(parts) < 2:
        raise ValueError("Domain name must contain at least one dot (e.g., example.com)")

    # Validate each part of the domain
    for i, part in enumerate(parts):
        if not part:
            raise ValueError("Domain name cannot have empty parts")

        if len(part) > 63:
            raise ValueError(f"Domain part '{part}' is too long (maximum 63 characters)")

        if part.startswith("-") or part.endswith("-"):
            raise ValueError(f"Domain part '{part}' cannot start or end with hyphen")

        # For the top-level domain (last part), be more strict
        if i == len(parts) - 1:
            # TLD should only contain letters (and possibly numbers for newer TLDs)
            if not re.match(r"^[a-zA-Z0-9]+$", part):
                raise ValueError(f"Top-level domain '{part}' contains invalid characters")
        else:
            # For subdomains and domain names, allow underscores (common in practice)
            # even though they're not strictly RFC compliant
            if not re.match(r"^[a-zA-Z0-9_-]+$", part):
                raise ValueError(
                    f"Domain part '{part}' contains invalid characters. Only letters, "
                    f"numbers, hyphens, and underscores are allowed"
                )

        # Ensure it doesn't start with a number (for domain names, not subdomains)
        if i == len(parts) - 2 and part[0].isdigit():  # Second to last part is the main domain
            # This is actually fine for many domains, so just continue
            pass

    return domain.lower()


def validate_empty_string(value: Any, default: str) -> str:
    """Convert empty string to default value.

    Args:
        value: Value to check
        default: Default value to return if empty

    Returns:
        Default value if input is empty string, otherwise the input value

    """
    if isinstance(value, str) and value.strip() == "":
        return default
    return str(value) if value is not None else default


def validate_config_filename(filename: str) -> str:
    """Validate configuration filename for security.

    This function requires a FULL filename including extension - no service name resolution
    is performed.

    Args:
        filename: Full configuration filename to validate (e.g., "jellyfin.subdomain.conf")

    Returns:
        Validated filename if safe

    Raises:
        ValueError: If filename contains dangerous patterns or is not a complete filename

    Note:
        Must be a full filename including extension, e.g., 'service.conf' or a sample file
        'service.conf.sample' — do not pass service names or partial paths

    """
    if not filename:
        raise ValueError("Configuration filename cannot be empty")

    # Normalize Unicode and trim whitespace to prevent bypass attempts
    try:
        normalized_filename = unicodedata.normalize("NFC", filename.strip())
    except (TypeError, ValueError) as e:
        raise ValueError(f"Configuration filename contains invalid Unicode: {str(e)}") from e

    # Basic length check (on normalized filename)
    if len(normalized_filename) > 255:
        raise ValueError("Configuration filename too long")

    # Check for path separators (reject any path components)
    if "/" in normalized_filename or "\\" in normalized_filename:
        raise ValueError("Path separators not allowed in configuration filenames")

    # Check for path traversal segments
    if ".." in normalized_filename:
        raise ValueError("Path traversal segments not allowed in configuration names")

    # Check for hidden files (files starting with dot)
    if normalized_filename.startswith("."):
        raise ValueError("Hidden files (starting with '.') not allowed")

    # Check for null bytes and other dangerous characters
    dangerous_chars = ["\0", "\n", "\r", "\t"]
    for char in dangerous_chars:
        if char in normalized_filename:
            raise ValueError(f"Invalid character in configuration name: {repr(char)}")

    # Use normalized filename for all subsequent validation
    filename = normalized_filename

    # Require full filename format - must end with .conf or .conf.sample extension
    if not filename.endswith(".conf") and not filename.endswith(".conf.sample"):
        raise ValueError(
            "Must be a full filename including extension, e.g., 'service.conf' or a sample file "
            "'service.conf.sample' — do not pass service names or partial paths"
        )

    # Additional validation: ensure it follows proper naming convention
    # Expected format: service.type.conf or service.type.conf.sample
    parts = filename.split(".")
    if filename.endswith(".conf.sample"):
        # For sample files: service.type.conf.sample (minimum 4 parts)
        if len(parts) < 4:
            raise ValueError(
                f"Must be a full filename with extension (got: '{filename}'). "
                "Use 'service.conf' or 'service.conf.sample' format."
            )
    else:
        # For regular files: service.type.conf (minimum 3 parts)
        if len(parts) < 3:
            raise ValueError(
                f"Must be a full filename with extension (got: '{filename}'). "
                "Use 'service.conf' or 'service.conf.sample' format."
            )

    # Check for suspicious patterns
    suspicious_patterns = [
        r"[<>:\"|?*\s]",  # Windows invalid chars + spaces
        r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)",  # Windows reserved names
        r"[\x00-\x1f\x7f]",  # Control characters including null bytes
        r"\|",  # Pipe character (command injection)
    ]

    for pattern in suspicious_patterns:
        if re.search(pattern, filename, re.IGNORECASE):
            raise ValueError("Invalid characters or patterns in configuration name")

    return filename


def validate_service_name(service_name: str, allow_emoji: bool = False) -> str:
    """Validate service name for security and format with Unicode support.

    Args:
        service_name: Service name to validate (supports Unicode)
        allow_emoji: Whether to allow emoji and other extended Unicode characters

    Returns:
        Validated and normalized service name if safe

    Raises:
        ValueError: If service name contains dangerous patterns

    """
    if not service_name:
        raise ValueError("Service name cannot be empty")

    # Normalize Unicode to NFC form to handle combining characters correctly
    try:
        normalized_name = unicodedata.normalize("NFC", service_name)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Service name contains invalid Unicode characters: {str(e)}") from e

    # Length validation (after normalization)
    if len(normalized_name) > 100:
        raise ValueError("Service name too long (maximum 100 characters)")

    # Validate Unicode characters with proper surrogate pair handling
    try:
        # Use our enhanced Unicode normalization which handles surrogates properly
        validated_unicode = normalize_unicode_text(normalized_name, remove_bom=True)
    except ValueError as e:
        raise ValueError(f"Service name contains invalid Unicode: {str(e)}") from e

    # Additional service name specific validation
    dangerous_categories_for_names = {
        "Cf",  # Format characters (like zero-width space) - problematic for names
        "Co",  # Private use area - could be used for spoofing
        "Cn",  # Unassigned characters - unstable
    }

    # Note: We no longer block 'Cs' (surrogates) here since
    # normalize_unicode_text handles them properly

    # Check characters with emoji awareness
    has_emoji = False
    for i, char in enumerate(validated_unicode):
        category = unicodedata.category(char)
        codepoint = ord(char)

        # Block dangerous Unicode categories (but allow surrogates if they're properly paired)
        if category in dangerous_categories_for_names:
            char_name = unicodedata.name(char, "UNKNOWN")
            raise ValueError(
                f"Service name contains dangerous Unicode character at position {i}: "
                f"U+{codepoint:04X} ({char_name})"
            )

        # Block most control characters except common ones
        if category == "Cc":  # Control characters
            raise ValueError(
                f"Service name contains control character at position {i}: U+{codepoint:04X}"
            )

        # Check for emoji and extended Unicode
        if codepoint > 0xFFFF:  # Extended Unicode plane (includes most emoji)
            has_emoji = True
            if not allow_emoji:
                char_name = unicodedata.name(char, "UNKNOWN")
                raise ValueError(
                    f"Service name contains emoji/extended Unicode character at position {i}: "
                    f"U+{codepoint:04X} ({char_name}). Set allow_emoji=True to permit."
                )

        # Check for common emoji ranges even in the Basic Multilingual Plane
        elif (
            0x2600 <= codepoint <= 0x26FF  # Miscellaneous Symbols
            or 0x2700 <= codepoint <= 0x27BF  # Dingbats
            or 0x1F300 <= codepoint <= 0x1F64F  # Miscellaneous Symbols and Pictographs
            or 0x1F680 <= codepoint <= 0x1F6FF  # Transport and Map Symbols
            or 0x1F900 <= codepoint <= 0x1F9FF
        ):  # Supplemental Symbols and Pictographs
            has_emoji = True
            if not allow_emoji:
                char_name = unicodedata.name(char, "UNKNOWN")
                raise ValueError(
                    f"Service name contains emoji character at position {i}: "
                    f"U+{codepoint:04X} ({char_name}). Set allow_emoji=True to permit."
                )

        # Block directional override characters (security risk)
        if char in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069":
            raise ValueError(
                f"Service name contains directional override character at position {i}: "
                f"U+{codepoint:04X}"
            )

    # Use the validated Unicode version for further processing
    normalized_name = validated_unicode

    # Character validation - allow Unicode letters, numbers, hyphens, underscores
    # And optionally emoji if allow_emoji is True
    if has_emoji and allow_emoji:
        # For names with emoji, do manual validation since regex is complex
        for i, char in enumerate(normalized_name):
            codepoint = ord(char)
            category = unicodedata.category(char)

            # Allow letters, numbers, hyphens, underscores, and emoji
            if not (
                category.startswith("L")  # Letters (any script)
                or category.startswith("N")  # Numbers (any script)
                or char in "_-"  # Allowed punctuation
                or codepoint > 0xFFFF  # Extended Unicode (emoji range)
                or (
                    0x2600 <= codepoint <= 0x26FF  # Miscellaneous Symbols
                    or 0x2700 <= codepoint <= 0x27BF  # Dingbats
                    or 0x1F300 <= codepoint <= 0x1F64F  # Miscellaneous Symbols and Pictographs
                    or 0x1F680 <= codepoint <= 0x1F6FF  # Transport and Map Symbols
                    or 0x1F900 <= codepoint <= 0x1F9FF
                )
            ):  # Supplemental Symbols and Pictographs
                char_name = unicodedata.name(char, "UNKNOWN")
                raise ValueError(
                    f"Service name contains invalid character at position {i}: "
                    f"U+{codepoint:04X} ({char_name})"
                )
    else:
        # Standard validation without emoji
        # Using Unicode property classes for proper international support
        try:
            # Try to use regex module for better Unicode support
            import regex  # type: ignore[import-untyped]

            if not regex.match(r"^[\p{L}\p{N}_-]+$", normalized_name):
                raise ValueError(
                    "Service name can only contain Unicode letters, numbers, hyphens, "
                    "and underscores"
                )
        except ImportError:
            # Fallback to basic validation if regex module not available
            # Allow Unicode word characters, hyphens, and underscores
            if not re.match(r"^[\w_-]+$", normalized_name, re.UNICODE):
                raise ValueError(
                    "Service name can only contain letters, numbers, hyphens, and underscores"
                ) from None

    # Must start with letter or number (Unicode-aware)
    if normalized_name:
        first_char = normalized_name[0]
        first_category = unicodedata.category(first_char)
        first_codepoint = ord(first_char)

        # Allow starting with letter, number, or emoji (if emoji are allowed)
        valid_start = (
            first_category.startswith("L")  # Letters
            or first_category.startswith("N")
        )  # Numbers

        if allow_emoji and has_emoji:
            # Also allow starting with emoji
            valid_start = valid_start or (
                first_codepoint > 0xFFFF  # Extended Unicode
                or (
                    0x2600 <= first_codepoint <= 0x26FF  # Miscellaneous Symbols
                    or 0x2700 <= first_codepoint <= 0x27BF  # Dingbats
                    or 0x1F300
                    <= first_codepoint
                    <= 0x1F64F  # Miscellaneous Symbols and Pictographs
                    or 0x1F680 <= first_codepoint <= 0x1F6FF  # Transport and Map Symbols
                    or 0x1F900 <= first_codepoint <= 0x1F9FF
                )  # Supplemental Symbols and Pictographs
            )

        if not valid_start:
            if allow_emoji:
                raise ValueError("Service name must start with a letter, number, or emoji")
            else:
                raise ValueError("Service name must start with a letter or number")

    # Additional security check: ensure no homograph attacks
    # Check for suspicious character combinations that might be used for spoofing
    ascii_lookalikes = {
        "а": "a",  # Cyrillic 'a'
        "е": "e",  # Cyrillic 'e'
        "о": "o",  # Cyrillic 'o'
        "р": "p",  # Cyrillic 'p'
        "с": "c",  # Cyrillic 'c'
        "х": "x",  # Cyrillic 'x'
        "у": "y",  # Cyrillic 'y'
        "κ": "k",  # Greek kappa
        "ο": "o",  # Greek omicron
        "ρ": "p",  # Greek rho
        "υ": "y",  # Greek upsilon
        # Add more as needed
    }

    # Warn about potential homograph characters (don't block, just log)
    for char in normalized_name:
        if char in ascii_lookalikes:
            # Don't block, but this could be logged for security monitoring
            pass

    # Check for mixed scripts that might indicate spoofing attempts
    scripts = set()
    for char in normalized_name:
        if char.isalpha():  # Only check alphabetic characters
            script = (
                unicodedata.name(char, "").split(" ")[0]
                if unicodedata.name(char, "")
                else "UNKNOWN"
            )
            if script not in ["LATIN", "UNKNOWN"]:
                scripts.add(script)

    # Allow mixed scripts but be aware of potential issues
    if len(scripts) > 2:  # More than 2 non-Latin scripts might be suspicious
        # Don't block, but this could be logged for review
        pass

    # Final length check after all processing
    if len(normalized_name) == 0:
        raise ValueError("Service name cannot be empty after normalization")

    return normalized_name


def normalize_unicode_text(text: str, remove_bom: bool = True) -> str:
    """Normalize Unicode text and optionally remove BOM characters.

    Args:
        text: Text to normalize
        remove_bom: Whether to remove Byte Order Mark characters

    Returns:
        Normalized Unicode text

    Raises:
        ValueError: If text contains invalid Unicode

    """
    if not isinstance(text, str):
        raise ValueError("Input must be a string")

    # Remove BOM characters if requested
    if remove_bom:
        # Remove common BOM characters
        bom_chars = [
            "\ufeff",  # UTF-8 BOM (also UTF-16/32 BOM when decoded)
            "\ufffe",  # UTF-16 LE BOM (incorrect byte order)
            "\u0000\ufeff",  # UTF-32 BE BOM
            "\ufeff\u0000",  # UTF-32 LE BOM
        ]

        for bom in bom_chars:
            if text.startswith(bom):
                text = text[len(bom) :]
                break

    # Normalize to NFC (Canonical Decomposition + Canonical Composition)
    # This handles combining characters and ensures consistent representation
    try:
        normalized = unicodedata.normalize("NFC", text)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Invalid Unicode characters in text: {str(e)}") from e

    # Check for problematic Unicode characters and handle surrogates properly
    problematic_chars = []
    i = 0
    while i < len(normalized):
        char = normalized[i]
        category = unicodedata.category(char)
        codepoint = ord(char)

        # Handle surrogate pairs properly
        if category == "Cs":  # Surrogate
            if 0xD800 <= codepoint <= 0xDBFF:  # High surrogate
                # Check if followed by low surrogate
                if i + 1 < len(normalized):
                    next_char = normalized[i + 1]
                    next_codepoint = ord(next_char)
                    if 0xDC00 <= next_codepoint <= 0xDFFF:  # Low surrogate
                        # Valid surrogate pair - reconstruct the full character
                        full_codepoint = (
                            0x10000 + ((codepoint - 0xD800) << 10) + (next_codepoint - 0xDC00)
                        )
                        # This is a valid extended Unicode character (emoji, etc.)
                        # Log for debugging if needed
                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug(
                                "Valid surrogate pair at position %d: U+%06X", i, full_codepoint
                            )
                        # Skip both surrogates since they form a valid pair
                        i += 2
                        continue
                    else:
                        # High surrogate not followed by low surrogate
                        problematic_chars.append(
                            f"Unpaired high surrogate U+{codepoint:04X} at position {i}"
                        )
                else:
                    # High surrogate at end of string
                    problematic_chars.append(
                        f"Unpaired high surrogate U+{codepoint:04X} at position {i}"
                    )
            elif 0xDC00 <= codepoint <= 0xDFFF:  # Low surrogate
                # Low surrogate should only appear after high surrogate
                problematic_chars.append(
                    f"Unpaired low surrogate U+{codepoint:04X} at position {i}"
                )

        # Check for other dangerous categories (but not surrogates now)
        elif category in [
            "Co",
            "Cn",
        ]:  # Private Use, Unassigned (excluding Cs which we handled above)
            problematic_chars.append(f"U+{codepoint:04X} at position {i}")

        # Check for directional override characters (security risk)
        elif char in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069":
            problematic_chars.append(f"Directional override U+{codepoint:04X} at position {i}")

        i += 1

    if problematic_chars:
        raise ValueError(
            f"Text contains problematic Unicode characters: {', '.join(problematic_chars[:5])}"
        )  # Limit to first 5

    return normalized


def detect_and_handle_encoding(content: bytes) -> str:
    """Detect encoding of byte content and decode to Unicode string.

    Args:
        content: Raw bytes to decode

    Returns:
        Decoded Unicode string with BOM removed

    Raises:
        ValueError: If content cannot be decoded as text

    """
    if not isinstance(content, bytes):
        raise ValueError("Input must be bytes")

    # Try UTF-8 first (most common)
    try:
        # Try UTF-8 with BOM detection
        text = content.decode("utf-8-sig")  # Automatically removes UTF-8 BOM
        return normalize_unicode_text(text, remove_bom=True)
    except UnicodeDecodeError:
        pass

    # Try UTF-16 (handles BOM automatically)
    try:
        text = content.decode("utf-16")
        return normalize_unicode_text(text, remove_bom=True)
    except UnicodeDecodeError:
        pass

    # Try UTF-32 (handles BOM automatically)
    try:
        text = content.decode("utf-32")
        return normalize_unicode_text(text, remove_bom=True)
    except UnicodeDecodeError:
        pass

    # Try common Western encodings in a realistic order:
    # cp1252 first (most common), then iso-8859-1, and finally latin-1 catch-all
    for encoding in ["cp1252", "iso-8859-1", "latin-1"]:
        try:
            text = content.decode(encoding)
            return normalize_unicode_text(text, remove_bom=True)
        except UnicodeDecodeError:
            continue

    raise ValueError("Unable to decode content as text - may be binary data")


def validate_file_content_safety(file_path: Path) -> bool:
    """Check if a file can be safely read as text.

    Args:
        file_path: Path to the file to check

    Returns:
        True if file appears to be text, False otherwise

    """
    try:
        # Check if the file is a symlink (security risk)
        if file_path.is_symlink():
            return False

        # Check if path is within allowed directory (prevent symlink attacks)
        real_path = file_path.resolve()

        # Additional security check: ensure resolved path is still within the expected directory
        # This prevents following symlinks to files outside the allowed directory
        try:
            # Get the parent directory of the original file path
            allowed_parent = file_path.parent.resolve()
            # Check if the resolved path is within the allowed directory
            real_path.relative_to(allowed_parent)
        except ValueError:
            # If relative_to fails, the resolved path is outside the allowed directory
            return False

        # Read first few bytes to detect binary content
        with open(real_path, "rb") as f:
            sample = f.read(512)  # Read first 512 bytes

        # Check for null bytes (common in binary files)
        if b"\0" in sample:
            return False

        # Try to decode using our enhanced encoding detection
        try:
            decoded_text = detect_and_handle_encoding(sample)
            # Additional check: ensure the decoded content is reasonable text
            is_decoded_empty_with_sample = len(decoded_text.strip()) == 0 and len(sample) > 0
            return not is_decoded_empty_with_sample
        except (ValueError, UnicodeDecodeError):
            return False

    except OSError:
        return False


def validate_upstream_port(port: int) -> int:
    """Validate upstream port number.

    Args:
        port: Port number to validate

    Returns:
        Validated port number

    Raises:
        ValueError: If port is invalid

    """
    if not isinstance(port, int):
        raise ValueError("Port must be an integer")

    if port < 1 or port > 65535:
        raise ValueError("Port must be between 1 and 65535")

    # Warn about commonly restricted ports
    restricted_ports = [22, 25, 53, 80, 443, 993, 995]
    if port in restricted_ports:
        # Don't raise error, but this could be logged
        pass

    return port


def validate_mcp_path(mcp_path: str) -> str:
    """Validate MCP path format for security and correctness.

    Args:
        mcp_path: MCP path to validate

    Returns:
        Validated MCP path

    Raises:
        ValueError: If MCP path is invalid

    """
    if not mcp_path:
        raise ValueError("MCP path cannot be empty")

    # Length validation
    if len(mcp_path) > 255:
        raise ValueError("MCP path is too long (maximum 255 characters)")

    # Must start with '/'
    if not mcp_path.startswith("/"):
        raise ValueError("MCP path must start with '/'")

    # Check for path traversal attempts
    if ".." in mcp_path:
        raise ValueError("Path traversal not allowed in MCP paths")

    # Check for null bytes and other dangerous characters
    dangerous_chars = ["\0", "\n", "\r", "\t"]
    for char in dangerous_chars:
        if char in mcp_path:
            raise ValueError(f"Invalid character in MCP path: {repr(char)}")

    # Allow only safe characters: letters, digits, '/', '-', '_', '.'
    if not re.match(r"^[a-zA-Z0-9/_.-]+$", mcp_path):
        raise ValueError(
            "MCP path can only contain letters, digits, '/', '-', '_', and '.' characters"
        )

    # Prevent double slashes (except at the start which is handled above)
    if "//" in mcp_path:
        raise ValueError("MCP path cannot contain consecutive slashes")

    # Cannot end with '/' unless it's the root path
    if mcp_path != "/" and mcp_path.endswith("/"):
        raise ValueError("MCP path cannot end with '/' (except root path)")

    # Additional security checks
    # Check for suspicious patterns that might be used for injection
    suspicious_patterns = [
        r"[<>:\"|?*]",  # Characters that could cause issues in configs
        r"[\x00-\x1f\x7f]",  # Control characters
        r"\|",  # Pipe character
        r";",  # Semicolon (command separator)
        r"&",  # Ampersand (command operator)
        r"\$",  # Dollar sign (variable expansion)
        r"`",  # Backtick (command substitution)
    ]

    for pattern in suspicious_patterns:
        if re.search(pattern, mcp_path):
            raise ValueError("MCP path contains invalid or potentially dangerous characters")

    return mcp_path
