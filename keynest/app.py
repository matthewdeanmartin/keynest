"""Tkinter application entry point for keynest.

Launch with ``python -m keynest.app`` or the ``keynest-gui`` console script.
"""

from __future__ import annotations

import sys

from keynest.upgrade_integration import exit_report, render_notice, startup_report


def main() -> int:
    """Launch the keynest GUI, returning a process exit code."""
    initial_notice = render_notice(startup_report())
    if initial_notice:
        print(initial_notice, file=sys.stderr)
    try:
        # Imported lazily so the CLI works even where tkinter is unavailable.
        from keynest.ui.main_window import run  # pylint: disable=import-outside-toplevel
    except ImportError as exc:  # pragma: no cover - tkinter missing on some builds
        print(f"Could not start the GUI (is tkinter installed?): {exc}", file=sys.stderr)
        return 1
    try:
        run()
    finally:
        final_notice = render_notice(exit_report())
        if final_notice and final_notice != initial_notice:
            print(final_notice, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
