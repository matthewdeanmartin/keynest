"""Command-line entry point for keynest."""

from __future__ import annotations

import argparse

from keynest.__about__ import __version__


def main() -> None:
    """Run the keynest CLI."""
    parser = argparse.ArgumentParser(
        prog="keynest",
        description=(
            "Developer secret workbench: a pure-Python keystore with GUI and "
            "CLI for OS keyring and AWS Secrets Manager"
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    # TODO: add subcommands here
    args = parser.parse_args()
    _ = args  # remove once subcommands are added


if __name__ == "__main__":
    main()
