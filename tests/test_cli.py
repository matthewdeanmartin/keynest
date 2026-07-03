"""Smoke tests for the CLI entry point."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from keynest import app


def test_import() -> None:
    """Package can be imported."""
    import keynest  # noqa: F401


def test_version() -> None:
    """Package exposes a version string."""
    from keynest.__about__ import __version__

    assert isinstance(__version__, str)
    assert __version__


def test_upgrade_subcommand_parses() -> None:
    """The parser should register the integrated upgrade subcommand."""
    from keynest.cli import build_parser

    args = build_parser().parse_args(["upgrade", "--check"])
    assert args.command == "upgrade"
    assert args._diu_check is True


def test_check_updates_subcommand_parses() -> None:
    """The parser should register the integrated check-updates subcommand."""
    from keynest.cli import build_parser

    args = build_parser().parse_args(["check-updates", "--no-network"])
    assert args.command == "check-updates"
    assert args._diu_no_network is True


def test_main_dispatches_upgrade_subcommand() -> None:
    """The integrated upgrade subcommand should return its dispatcher exit code."""
    from keynest.cli import main

    with patch("keynest.cli.run_command", return_value=10) as dispatcher:
        rc = main(["upgrade", "--check"])

    assert rc == 10
    dispatcher.assert_called_once()


def test_app_main_prints_distinct_startup_and_exit_notices(capsys: pytest.CaptureFixture[str]) -> None:
    """The GUI wrapper should print startup and shutdown notices to stderr."""
    startup_marker = object()
    exit_marker = object()

    def fake_render_notice(report: object | None) -> str:
        if report is startup_marker:
            return "startup notice"
        if report is exit_marker:
            return "exit notice"
        return ""

    with (
        patch("keynest.app.startup_report", return_value=startup_marker),
        patch("keynest.app.exit_report", return_value=exit_marker),
        patch("keynest.app.render_notice", side_effect=fake_render_notice),
        patch("keynest.ui.main_window.run"),
    ):
        rc = app.main()

    assert rc == 0
    assert capsys.readouterr().err == "startup notice\nexit notice\n"


def test_app_main_suppresses_duplicate_exit_notice(capsys: pytest.CaptureFixture[str]) -> None:
    """The GUI wrapper should not print the same notice twice."""
    marker = object()

    with (
        patch("keynest.app.startup_report", return_value=marker),
        patch("keynest.app.exit_report", return_value=marker),
        patch("keynest.app.render_notice", return_value="same notice"),
        patch("keynest.ui.main_window.run"),
    ):
        rc = app.main()

    assert rc == 0
    assert capsys.readouterr().err == "same notice\n"
