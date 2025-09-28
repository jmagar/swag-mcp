"""MCP-specific token optimization utilities for efficient AI interactions."""

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class MCPTokenOptimizer:
    """Token-efficient response optimizer for MCP transport."""

    def __init__(self, max_tokens: int = 4000, compression_ratio: float = 0.7):
        """Initialize token optimizer with max tokens and compression ratio."""
        self.max_tokens = max_tokens
        self.compression_ratio = compression_ratio
        self.estimated_token_ratio = 4  # Average characters per token

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count from text length.

        Args:
            text: Text to analyze

        Returns:
            Estimated token count

        """
        # Rough estimation: 1 token ≈ 4 characters for English text
        # This is a conservative estimate for planning purposes
        return len(text) // self.estimated_token_ratio

    def optimize_response(self, response: str, context: dict[str, Any]) -> str:
        """Optimize response for MCP transport efficiency.

        Args:
            response: Original response text
            context: Context information for optimization decisions

        Returns:
            Optimized response text

        """
        if not response:
            return response

        estimated_tokens = self.estimate_tokens(response)

        if estimated_tokens <= self.max_tokens:
            return response  # No optimization needed

        logger.debug(
            f"Optimizing response: {estimated_tokens} estimated tokens > {self.max_tokens}"
        )

        # Apply optimization strategies based on context
        action = context.get("action", "unknown")

        if action == "list":
            return self._optimize_list_response(response, context)
        elif action == "view":
            return self._optimize_view_response(response, context)
        elif action == "logs":
            return self._optimize_logs_response(response, context)
        elif action == "create":
            return self._optimize_create_response(response, context)
        else:
            return self._optimize_generic_response(response)

    def _optimize_list_response(self, response: str, context: dict[str, Any]) -> str:
        """Optimize list operation responses.

        Args:
            response: Original response
            context: Context with list details

        Returns:
            Optimized list response

        """
        # For list responses, prioritize summary over details
        lines = response.split('\n')

        # Keep header information
        optimized_lines = []
        summary_added = False

        for line in lines:
            if not summary_added and ('Total:' in line or 'Found' in line):
                optimized_lines.append(line)
                summary_added = True
            elif line.startswith('##') or line.startswith('###'):
                # Keep section headers
                optimized_lines.append(line)
            elif line.strip() and not line.startswith('- '):
                # Keep non-list items
                optimized_lines.append(line)
            elif line.startswith('- ') and len(optimized_lines) < 20:
                # Keep first 20 list items
                optimized_lines.append(line)

        # Add truncation notice if needed
        if len(lines) > len(optimized_lines):
            remaining = len(lines) - len(optimized_lines)
            optimized_lines.append(f"\n... and {remaining} more entries")
            optimized_lines.append("\n💡 Use 'view' action for detailed configuration content")

        return '\n'.join(optimized_lines)

    def _optimize_view_response(self, response: str, context: dict[str, Any]) -> str:
        """Optimize view operation responses.

        Args:
            response: Original response
            context: Context with view details

        Returns:
            Optimized view response

        """
        # For view responses, use smart truncation with important sections

        # Check if it's a configuration file
        if 'server {' in response or 'location /' in response:
            return self._optimize_config_content(response)

        # Generic text optimization
        return self._smart_truncate(response, preserve_structure=True)

    def _optimize_logs_response(self, response: str, context: dict[str, Any]) -> str:
        """Optimize log responses with smart sampling.

        Args:
            response: Original log response
            context: Context with log details

        Returns:
            Optimized log response

        """
        lines = response.split('\n')

        if len(lines) <= 50:
            return response  # Small enough already

        # Keep header and footer, sample middle
        header_lines = lines[:5]
        footer_lines = lines[-10:]

        # Sample from middle
        middle_lines = lines[5:-10]
        sample_size = min(20, len(middle_lines))

        if sample_size < len(middle_lines):
            # Take every nth line for sampling
            step = len(middle_lines) // sample_size
            sampled_middle = [
                middle_lines[i] for i in range(0, len(middle_lines), step)
            ][:sample_size]
        else:
            sampled_middle = middle_lines

        # Combine sections
        optimized_lines = (
            header_lines +
            [f"\n... showing {sample_size} of {len(middle_lines)} middle entries ...\n"] +
            sampled_middle +
            ["\n... showing last 10 entries ...\n"] +
            footer_lines
        )

        return '\n'.join(optimized_lines)

    def _optimize_create_response(self, response: str, context: dict[str, Any]) -> str:
        """Optimize create operation responses.

        Args:
            response: Original response
            context: Context with create details

        Returns:
            Optimized create response

        """
        # For create responses, prioritize success confirmation and health check
        lines = response.split('\n')
        optimized_lines = []

        in_config_content = False
        health_check_started = False

        for line in lines:
            if '# Configuration Content:' in line:
                in_config_content = True
                optimized_lines.append(line)
                optimized_lines.append("... [configuration content truncated for brevity] ...")
                continue
            elif '✅ Health check' in line or '⚠️ Health check' in line:
                health_check_started = True
                in_config_content = False

            if not in_config_content or health_check_started:
                optimized_lines.append(line)

        return '\n'.join(optimized_lines)

    def _optimize_config_content(self, content: str) -> str:
        """Optimize nginx configuration content for readability.

        Args:
            content: Configuration file content

        Returns:
            Optimized configuration content

        """
        lines = content.split('\n')
        important_lines: list[str] = []

        # Patterns for important configuration lines
        important_patterns = [
            r'server\s*{',
            r'server_name\s+',
            r'listen\s+',
            r'location\s+/',
            r'proxy_pass\s+',
            r'include\s+',
            r'#.*?auth',  # Authentication related comments
            r'#.*?MCP',   # MCP related comments
            r'}',
        ]

        pattern = '|'.join(important_patterns)
        compiled_pattern = re.compile(pattern, re.IGNORECASE)

        for line in lines:
            stripped = line.strip()
            if (compiled_pattern.search(line) or
                not stripped or
                stripped.startswith('#')) or len(important_lines) < 30:
                important_lines.append(line)

        if len(lines) > len(important_lines):
            important_lines.append(
                f"\n# ... {len(lines) - len(important_lines)} additional lines truncated ..."
            )

        return '\n'.join(important_lines)

    def _optimize_generic_response(self, response: str) -> str:
        """Apply generic optimization strategies.

        Args:
            response: Original response

        Returns:
            Optimized response

        """
        return self._smart_truncate(response, preserve_structure=True)

    def _smart_truncate(self, text: str, preserve_structure: bool = True) -> str:
        """Smart truncation that preserves important content.

        Args:
            text: Text to truncate
            preserve_structure: Whether to preserve structure (headers, lists)

        Returns:
            Truncated text

        """
        target_length = int(self.max_tokens * self.estimated_token_ratio * self.compression_ratio)

        if len(text) <= target_length:
            return text

        if not preserve_structure:
            return text[:target_length] + "\n\n... [truncated for brevity]"

        lines = text.split('\n')
        preserved_lines = []
        current_length = 0

        # Priority order: headers, important markers, regular content
        priority_patterns = [
            (r'^#{1,3}\s+', 10),      # Headers (high priority)
            (r'^\*\*.*?\*\*', 8),     # Bold text (high priority)
            (r'✅|⚠️|❌|🔍|💡', 9),    # Status emojis (high priority)
            (r'^-\s+', 5),            # List items (medium priority)
            (r'^\d+\.', 5),           # Numbered lists (medium priority)
            (r'^>', 4),               # Quotes (medium priority)
        ]

        # First pass: collect high-priority lines
        for line in lines:
            line_priority = 1  # Default priority
            for pattern, priority in priority_patterns:
                if re.match(pattern, line.strip()):
                    line_priority = priority
                    break

            line_length = len(line) + 1  # +1 for newline
            if current_length + line_length <= target_length or line_priority >= 8:
                preserved_lines.append(line)
                current_length += line_length
            elif line_priority >= 5:
                # Truncate long medium-priority lines
                # Reserve space for truncation marker
                remaining = target_length - current_length - 50
                if remaining > 20:
                    preserved_lines.append(line[:remaining] + "...")
                    current_length = target_length
                    break

        if len(lines) > len(preserved_lines):
            preserved_lines.append(f"\n... [showing {len(preserved_lines)} of {len(lines)} lines]")

        return '\n'.join(preserved_lines)

    def create_summary_response(
        self,
        full_response: str,
        context: dict[str, Any],
        summary_length: int = 200
    ) -> str:
        """Create a concise summary response.

        Args:
            full_response: Complete response text
            context: Context for summary generation
            summary_length: Target summary length in characters

        Returns:
            Summary response

        """
        action = context.get("action", "unknown")

        # Extract key information based on action type
        if action == "list":
            return self._create_list_summary(full_response, summary_length)
        elif action == "create":
            return self._create_create_summary(full_response, summary_length)
        elif action == "health_check":
            return self._create_health_summary(full_response, summary_length)
        else:
            # Generic summary - first paragraph + key stats
            lines = full_response.split('\n')
            summary_lines = []

            for line in lines[:5]:  # First 5 lines
                if line.strip():
                    summary_lines.append(line.strip())

            summary = ' '.join(summary_lines)
            if len(summary) > summary_length:
                summary = summary[:summary_length-3] + "..."

            return summary

    def _create_list_summary(self, response: str, max_length: int) -> str:
        """Create summary for list responses."""
        # Extract count information
        count_match = re.search(r'Total:\s*(\d+)', response)
        if count_match:
            count = count_match.group(1)
            return f"Found {count} configurations. Use 'view' for details on specific configs."

        return "Configuration list retrieved successfully."

    def _create_create_summary(self, response: str, max_length: int) -> str:
        """Create summary for create responses."""
        # Extract filename and health status
        filename_match = re.search(r'Created configuration:\s*([^\n]+)', response)
        health_match = re.search(r'(✅|⚠️)[^:]*:[^:]*:([^\\n]+)', response)

        filename = filename_match.group(1) if filename_match else "configuration"
        health = health_match.group(2).strip() if health_match else "status unknown"

        return f"Created {filename}. Health: {health}"

    def _create_health_summary(self, response: str, max_length: int) -> str:
        """Create summary for health check responses."""
        if "✅" in response:
            return "Health check passed"
        elif "⚠️" in response:
            return "Health check failed"
        else:
            return "Health check completed"

    def optimize_for_streaming(self, content: str, chunk_size: int = 1000) -> list[str]:
        """Optimize content for streaming delivery.

        Args:
            content: Content to stream
            chunk_size: Target size per chunk

        Returns:
            List of optimized chunks

        """
        if len(content) <= chunk_size:
            return [content]

        # Split on natural boundaries
        chunks = []
        lines = content.split('\n')
        current_chunk: list[str] = []
        current_size = 0

        for line in lines:
            line_size = len(line) + 1  # +1 for newline

            if current_size + line_size > chunk_size and current_chunk:
                # Finish current chunk
                chunks.append('\n'.join(current_chunk))
                current_chunk = [line]
                current_size = line_size
            else:
                current_chunk.append(line)
                current_size += line_size

        # Add final chunk
        if current_chunk:
            chunks.append('\n'.join(current_chunk))

        return chunks


# Factory functions and utilities

def create_token_optimizer(max_tokens: int = 4000) -> MCPTokenOptimizer:
    """Create a token optimizer instance.

    Args:
        max_tokens: Maximum tokens for responses

    Returns:
        MCPTokenOptimizer instance

    """
    return MCPTokenOptimizer(max_tokens)


def optimize_json_response(data: dict[str, Any], max_tokens: int = 4000) -> dict[str, Any]:
    """Optimize JSON response data for token efficiency.

    Args:
        data: JSON data to optimize
        max_tokens: Maximum token limit

    Returns:
        Optimized JSON data

    """
    json_str = json.dumps(data, indent=2)
    estimated_tokens = len(json_str) // 4

    if estimated_tokens <= max_tokens:
        return data

    # Apply JSON-specific optimizations
    optimized_data = data.copy()

    # Truncate large arrays
    for key, value in optimized_data.items():
        if isinstance(value, list) and len(value) > 10:
            optimized_data[key] = value[:10]
            optimized_data[f"{key}_truncated"] = f"Showing 10 of {len(value)} items"
        elif isinstance(value, str) and len(value) > 1000:
            optimized_data[key] = value[:1000] + "... [truncated]"

    return optimized_data


def create_dual_response(
    full_content: str,
    context: dict[str, Any],
    max_tokens: int = 4000
) -> tuple[str, str]:
    """Create dual response: optimized version + summary.

    Args:
        full_content: Complete response content
        context: Context for optimization
        max_tokens: Token limit

    Returns:
        Tuple of (optimized_response, summary_response)

    """
    optimizer = MCPTokenOptimizer(max_tokens)

    optimized = optimizer.optimize_response(full_content, context)
    summary = optimizer.create_summary_response(full_content, context)

    return optimized, summary
