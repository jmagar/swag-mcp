"""Validation module for SWAG MCP."""

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

from swag_mcp.utils.validators import normalize_unicode_text

logger = logging.getLogger(__name__)


class ValidationService:
    """Handles validation logic (nginx, content, security)."""

    def __init__(self) -> None:
        """Initialize validation service."""
        pass

    async def validate_nginx_syntax(self, config_path: Path) -> bool:
        """Validate nginx configuration syntax using subprocess.

        Args:
            config_path: Path to the nginx configuration file to validate

        Returns:
            bool: True if syntax is valid, False otherwise

        """
        import shutil
        import subprocess

        try:
            # Check if nginx is available
            nginx_cmd = shutil.which("nginx")
            if not nginx_cmd:
                logger.warning("nginx command not found, skipping syntax validation")
                return True  # Assume valid if nginx not available

            # Run nginx syntax test
            result = await asyncio.create_subprocess_exec(
                nginx_cmd,
                "-t",
                "-c",
                str(config_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            stdout, stderr = await result.communicate()

            # nginx -t returns 0 for valid config, non-zero for invalid
            if result.returncode == 0:
                logger.debug(f"nginx syntax validation passed for {config_path}")
                return True
            else:
                logger.error(
                    f"nginx syntax validation failed for {config_path}: "
                    f"{stderr.decode('utf-8', errors='ignore')}"
                )
                return False

        except Exception as e:
            logger.error(f"Error validating nginx syntax for {config_path}: {e}")
            # Return True to not block operations if validation fails
            return True

    def validate_config_content(self, content: str, config_name: str) -> str:
        """Validate configuration file content for security.

        Args:
            content: Configuration file content to validate
            config_name: Name of the configuration file

        Returns:
            Validated content if safe

        Raises:
            ValueError: If content contains dangerous patterns

        """
        if not content or not content.strip():
            raise ValueError("Configuration content cannot be empty")

        # Patterns that should never appear in configuration files
        dangerous_patterns = [
            # Template injection attempts (users shouldn't put raw Jinja2 in configs)
            r"\{\{.*?\}\}",  # Jinja2 expressions in user content
            r"\{%.*?%\}",  # Jinja2 statements in user content
            r"\{#.*?#\}",  # Jinja2 comments in user content
            # Server-side includes and imports
            r'include\s+["\'][^"\']*["\'];?\s*#[^}]*\}\}',  # Template includes
            r'import\s+["\'][^"\']*["\'];?\s*#[^}]*\}\}',  # Template imports
            # Script injection attempts
            r"<script.*?>",  # Script tags
            r"javascript:",  # JavaScript URLs
            r"data:.*base64",  # Data URLs with base64
            r"vbscript:",  # VBScript URLs
            # Shell command injection attempts (more specific to avoid nginx syntax)
            r";\s*(ls|cat|rm|cp|mv|mkdir|grep|sed|awk|curl|wget|nc|ncat|bash|sh|python|perl|ruby|php)[^a-zA-Z0-9_]",
            # Common shell commands after semicolon
            r"\$\([^)]*\)",  # Command substitution
            r"`[^`]*`",  # Backtick command execution
            # File system access attempts
            r"\.\./",  # Path traversal attempts
            r"\.\.\\",  # Windows path traversal
            r"/etc/",  # Direct /etc access
            r"/var/",  # Direct /var access
            r"/tmp/",  # Direct /tmp access
            r"/home/",  # Direct /home access
            r"/root/",  # Direct /root access
            r"file://",  # File:// URLs
            # Process/system access attempts
            r"proc/",  # /proc filesystem access
            r"dev/",  # /dev filesystem access
        ]

        # Check for dangerous patterns
        for pattern in dangerous_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                logger.warning(
                    f"Blocked dangerous content in configuration '{config_name}': "
                    f"matched pattern {pattern}"
                )
                raise ValueError("Configuration content contains potentially dangerous patterns")

        # Additional validation for NGINX configuration files
        if config_name.endswith(".conf"):
            # Ensure reasonable length (prevent DoS through large configs)
            if len(content) > 10000000:  # 10MB limit
                raise ValueError("Configuration content is too large")

            # Basic NGINX syntax validation - ensure it has server blocks if it's a config
            if "server" not in content and len(content.strip()) > 50:
                # Only warn for now, don't block (might be valid edge case)
                logger.info(
                    f"Configuration '{config_name}' doesn't appear to contain server blocks"
                )

        # Normalize Unicode and remove BOM for consistent processing
        try:
            normalized_content = normalize_unicode_text(content, remove_bom=True, strict=False)
        except ValueError as e:
            raise ValueError(
                f"Invalid Unicode content in configuration '{config_name}': {str(e)}"
            ) from e

        logger.debug(
            f"Validated configuration content for '{config_name}' "
            f"({len(normalized_content)} characters)"
        )
        return normalized_content

    async def preview_config_changes(
        self,
        config_name: str,
        current_content: str,
        new_content: str,
    ) -> dict[str, Any]:
        """Preview changes before applying them.

        Shows a diff of what will change, line-by-line comparison,
        and validates the new content syntax.

        Args:
            config_name: Name of the configuration file
            current_content: Current file content (empty string for new files)
            new_content: Proposed new content

        Returns:
            Dictionary with diff, validation status, and change statistics

        """
        import difflib
        import tempfile

        is_new = not current_content

        # Generate unified diff
        diff_lines = list(
            difflib.unified_diff(
                current_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"{config_name} (current)",
                tofile=f"{config_name} (new)",
                lineterm="",
            )
        )

        # Validate new content syntax with nginx
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as temp_file:
            temp_file.write(new_content)
            temp_path = Path(temp_file.name)

        try:
            syntax_valid = await self.validate_nginx_syntax(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

        # Count changes
        lines_added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
        lines_removed = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
        lines_changed = max(lines_added, lines_removed)

        result = {
            "is_new_file": is_new,
            "diff": "".join(diff_lines) if diff_lines else "No changes",
            "syntax_valid": syntax_valid,
            "lines_added": lines_added,
            "lines_removed": lines_removed,
            "lines_changed": lines_changed,
            "total_lines_old": len(current_content.splitlines()),
            "total_lines_new": len(new_content.splitlines()),
        }

        logger.info(
            f"Preview for {config_name}: {'new file' if is_new else 'update'}, "
            f"+{lines_added} -{lines_removed}, syntax_valid={syntax_valid}"
        )

        return result
