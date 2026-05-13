"""Entry point for running SWAG MCP server as a module."""

import argparse
import asyncio
from pathlib import Path

from .server import main
from .setup import repair_setup


def cli() -> None:
    """Run the SWAG MCP command-line interface."""
    parser = argparse.ArgumentParser(prog="swag_mcp")
    subparsers = parser.add_subparsers(dest="command")

    setup_parser = subparsers.add_parser("setup")
    setup_subparsers = setup_parser.add_subparsers(dest="setup_command")
    repair_parser = setup_subparsers.add_parser("repair")
    repair_parser.add_argument("--home", type=Path, default=None)

    args = parser.parse_args()

    if args.command == "setup" and args.setup_command == "repair":
        result = repair_setup(home_dir=args.home)
        print(f"repaired config: {result.config_path}")
        print(f"repaired env: {result.env_path}")
        return

    asyncio.run(main())


if __name__ == "__main__":
    cli()
