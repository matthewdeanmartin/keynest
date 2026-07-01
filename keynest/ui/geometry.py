"""Window geometry helpers: sizing and centering Tk windows."""

from __future__ import annotations

import tkinter as tk

# A top-level window: ``Tk`` or ``Toplevel``. Both provide the ``winfo_*``
# (from ``Misc``) and ``geometry`` (from ``Wm``) methods these helpers use.
Window = tk.Tk | tk.Toplevel


def center_window(window: Window, width: int, height: int) -> None:
    """Size ``window`` to ``width``x``height`` and center it on the screen.

    Args:
        window: The Tk window (``Tk`` or ``Toplevel``) to position.
        width: Desired window width in pixels.
        height: Desired window height in pixels.
    """
    screen_w = window.winfo_screenwidth()
    screen_h = window.winfo_screenheight()
    x = max((screen_w - width) // 2, 0)
    y = max((screen_h - height) // 2, 0)
    window.geometry(f"{width}x{height}+{x}+{y}")


def center_fraction(window: Window, fraction: float) -> None:
    """Size ``window`` to ``fraction`` of the screen and center it.

    Args:
        window: The Tk window to position.
        fraction: Side length as a fraction of the screen (e.g. ``0.75`` for
            a window 75% of the screen's width and height).
    """
    width = int(window.winfo_screenwidth() * fraction)
    height = int(window.winfo_screenheight() * fraction)
    center_window(window, width, height)
