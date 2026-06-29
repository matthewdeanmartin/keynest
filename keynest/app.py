"""Tkinter application entry point for keynest.

Launch with ``python -m keynest.app`` or the ``keynest-gui`` console script.
"""

from __future__ import annotations

import sys


def main() -> int:
    """Launch the keynest GUI, returning a process exit code."""
    try:
        # Imported lazily so the CLI works even where tkinter is unavailable.
        from keynest.ui.main_window import run  # pylint: disable=import-outside-toplevel
    except ImportError as exc:  # pragma: no cover - tkinter missing on some builds
        print(f"Could not start the GUI (is tkinter installed?): {exc}", file=sys.stderr)
        return 1
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
