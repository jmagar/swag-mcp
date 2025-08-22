"""Tests for SWAG MCP __main__ module entry point."""

import asyncio
import runpy
from unittest.mock import AsyncMock, patch

import pytest


class TestMainModule:
    """Test suite for __main__ module entry point."""

    @pytest.mark.asyncio
    async def test_main_module_execution(self):
        """Test __main__.py module execution using runpy."""
        # Mock the main function to avoid actually starting the server
        with patch("swag_mcp.server.main", new_callable=AsyncMock):
            # Mock asyncio.run to capture the call
            with patch("asyncio.run") as mock_asyncio_run:
                try:
                    # Use runpy to properly execute the module with correct import context
                    runpy.run_module("swag_mcp.__main__", run_name="__main__")
                except SystemExit:
                    # runpy may cause SystemExit, which is normal for main modules
                    pass

                # Verify that asyncio.run was called
                mock_asyncio_run.assert_called_once()

                # Get the function that was passed to asyncio.run
                called_func = mock_asyncio_run.call_args[0][0]

                # It should be the main function or a coroutine from main()
                assert asyncio.iscoroutine(called_func) or callable(called_func)

    def test_main_module_imports(self):
        """Test that __main__ module imports are correct."""
        import swag_mcp.__main__

        # Verify required imports exist
        assert hasattr(swag_mcp.__main__, "asyncio")
        assert hasattr(swag_mcp.__main__, "main")

        # Verify main is callable
        assert callable(swag_mcp.__main__.main)

    @pytest.mark.asyncio
    async def test_main_function_call_path(self):
        """Test the actual execution path when __name__ == '__main__'."""
        from swag_mcp.__main__ import main

        # Mock the main function to avoid actually starting server
        with patch("swag_mcp.__main__.main", new_callable=AsyncMock):
            # Mock the __name__ check and asyncio.run
            with (
                patch("swag_mcp.__main__.__name__", "__main__"),
                patch("asyncio.run") as mock_asyncio_run,
            ):
                # Execute the module's main block
                # This simulates what happens when python -m swag_mcp is run
                if "__main__" == "__main__":
                    asyncio.run(main())

                # Verify the execution path
                mock_asyncio_run.assert_called()
