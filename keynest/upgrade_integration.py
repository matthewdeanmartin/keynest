"""Helpers for embedding do_i_need_to_upgrade into keynest."""

from __future__ import annotations

import argparse
import io
import sys

from do_i_need_to_upgrade import add_check_command, add_upgrade_command, run_if_upgrade_command
from do_i_need_to_upgrade.api import check_for_updates
from do_i_need_to_upgrade.report import Report
from do_i_need_to_upgrade.settings import Settings

DIST_NAME = "keynest"
CHECK_UPDATES_COMMAND = "check-updates"
UPGRADE_COMMAND = "upgrade"


def settings() -> Settings:
    """Return keynest's embedded update-check settings."""
    return Settings(dist_name=DIST_NAME, position="start", notify="return-only")


def add_commands(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register integrated do_i_need_to_upgrade subcommands."""
    active_settings = settings()
    add_upgrade_command(subparsers, DIST_NAME, command=UPGRADE_COMMAND, settings=active_settings)
    add_check_command(subparsers, DIST_NAME, command=CHECK_UPDATES_COMMAND, settings=active_settings)
    subparsers.choices[CHECK_UPDATES_COMMAND].epilog = (
        "exit codes: 0 = up to date, 10 = upgrades available, 1 = check errors. "
        "Set DO_I_NEED_TO_UPGRADE=off to disable update checks entirely."
    )


def run_command(args: argparse.Namespace) -> int | None:
    """Dispatch integrated update-related subcommands."""
    return run_if_upgrade_command(args)


def startup_report() -> Report | None:
    """Kick off the background refresh and return the current cache-backed report."""
    report = check_for_updates(settings=settings())
    return report if not report.is_empty else None


def exit_report() -> Report | None:
    """Read the refreshed cache on exit without doing more network I/O."""
    report = check_for_updates(settings=settings().replace(allow_network=False, notify="return-only"))
    return report if not report.is_empty else None


def render_notice(report: Report | None) -> str:
    """Render a user-facing update notice for stderr."""
    if report is None:
        return ""
    return report.render_text(stream=sys.stderr)


def cached_notice() -> str:
    """Plain-text notice from the local cache only (no network, no ANSI).

    Safe to call from GUI code: color is disabled by rendering against a
    non-tty stream, so the text can go straight into Tk widgets.
    """
    report = exit_report()
    return report.render_text(stream=io.StringIO()) if report is not None else ""


def fresh_notice() -> str:
    """Synchronously refresh from PyPI and render a plain-text notice.

    Blocks on network I/O; call from a worker thread in GUI code. Returns
    an empty string when keynest is up to date. End-user kill switches
    (``DO_I_NEED_TO_UPGRADE=off``/``no-network``) are honored.
    """
    report = check_for_updates(settings=settings().replace(position="end", notify="return-only"))
    return report.render_text(stream=io.StringIO())


__all__ = [
    "CHECK_UPDATES_COMMAND",
    "DIST_NAME",
    "UPGRADE_COMMAND",
    "add_commands",
    "cached_notice",
    "exit_report",
    "fresh_notice",
    "render_notice",
    "run_command",
    "settings",
    "startup_report",
]
