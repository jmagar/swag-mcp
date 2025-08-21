"""Logging configuration for SWAG MCP server with dual output (console + files)."""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any

from .config import config


def setup_logging() -> None:
    """Configure logging with console and file handlers.

    Sets up two log files:
    - swag-mcp.log: Main application logs
    - swag-middleware.log: Middleware-specific logs

    Both files use rotation that clears the file when size limit is reached.
    Console logging continues to work as before.
    """
    # Create log directory if it doesn't exist
    if config.log_file_enabled:
        log_dir = Path(config.log_directory)
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            print(f"Warning: Cannot create log directory {log_dir}: {e}")
            print("File logging will be disabled, console logging will continue")
            config.log_file_enabled = False

    # Clear any existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    # Set root log level
    root_logger.setLevel(getattr(logging, config.log_level.upper()))

    # Create formatter
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # 1. Console handler - for all logs
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(getattr(logging, config.log_level.upper()))
    root_logger.addHandler(console_handler)

    if not config.log_file_enabled:
        return

    # 2. Main application log file handler
    main_log_file = Path(config.log_directory) / "swag-mcp.log"
    main_file_handler = logging.handlers.RotatingFileHandler(
        filename=main_log_file,
        maxBytes=config.log_file_max_bytes,
        backupCount=0,  # Don't keep old files, just clear when size limit hit
        encoding="utf-8",
    )
    main_file_handler.setFormatter(formatter)
    main_file_handler.setLevel(getattr(logging, config.log_level.upper()))

    # 3. Middleware log file handler
    middleware_log_file = Path(config.log_directory) / "swag-middleware.log"
    middleware_file_handler = logging.handlers.RotatingFileHandler(
        filename=middleware_log_file,
        maxBytes=config.log_file_max_bytes,
        backupCount=0,  # Don't keep old files, just clear when size limit hit
        encoding="utf-8",
    )
    middleware_file_handler.setFormatter(formatter)
    middleware_file_handler.setLevel(getattr(logging, config.log_level.upper()))

    # Configure main application logger
    # Root logger gets console + main file
    root_logger.addHandler(main_file_handler)

    # Configure middleware loggers to use middleware file instead
    middleware_loggers = [
        "swag_mcp.middleware",
        "swag_mcp.timing",
        "fastmcp.middleware",
        "fastmcp.server.middleware",
    ]

    for logger_name in middleware_loggers:
        middleware_logger = logging.getLogger(logger_name)
        # Remove inheritance to prevent writing to main log file
        middleware_logger.propagate = False
        # Add console + middleware file handlers
        middleware_logger.addHandler(console_handler)
        middleware_logger.addHandler(middleware_file_handler)
        middleware_logger.setLevel(getattr(logging, config.log_level.upper()))


def get_logger_config() -> dict[str, Any]:
    """Get current logging configuration for debugging.

    Returns:
        Dictionary with current logging settings

    """
    return {
        "log_level": config.log_level,
        "log_file_enabled": config.log_file_enabled,
        "log_directory": str(config.log_directory),
        "log_file_max_bytes": config.log_file_max_bytes,
        "console_logging": True,  # Always enabled
    }


__all__ = ["setup_logging", "get_logger_config"]
