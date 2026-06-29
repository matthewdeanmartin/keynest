"""Clipboard helper with an auto-clear timeout, built on Tkinter.

Uses Tkinter's clipboard (no ``pyperclip`` dependency). Copying a secret
schedules an automatic clear after a configurable interval so the value does
not linger in shared OS clipboard state.
"""

from __future__ import annotations

import contextlib
import tkinter as tk
from collections.abc import Callable

DEFAULT_CLEAR_SECONDS = 30

CLIPBOARD_WARNING = (
    "Clipboard is shared OS state. Other apps may be able to read it. "
    "Prefer generated code or `keynest run` when possible."
)


class ClipboardManager:
    """Copies values to the Tk clipboard and clears them after a timeout."""

    def __init__(self, widget: tk.Misc, clear_seconds: int = DEFAULT_CLEAR_SECONDS) -> None:
        """Bind the manager to a Tk widget and configure the clear interval."""
        self._widget = widget
        self.clear_seconds = clear_seconds
        self._pending_after: str | None = None
        self._copied_value: str | None = None

    def copy(self, value: str, on_clear: Callable[[], None] | None = None) -> None:
        """Copy ``value`` to the clipboard and schedule an auto-clear.

        Args:
            value: The text to place on the clipboard.
            on_clear: Optional callback invoked after the clipboard is cleared.
        """
        self._cancel_pending()
        self._widget.clipboard_clear()
        self._widget.clipboard_append(value)
        self._copied_value = value
        delay_ms = max(0, self.clear_seconds) * 1000
        self._pending_after = self._widget.after(delay_ms, lambda: self._auto_clear(on_clear))

    def clear_now(self) -> None:
        """Immediately clear the clipboard if it still holds our value."""
        self._cancel_pending()
        self._auto_clear(None)

    def _auto_clear(self, on_clear: Callable[[], None] | None) -> None:
        # Only clear if the clipboard still contains what we put there, so we
        # don't stomp on something the user copied afterwards.
        try:
            current: str | None = self._widget.clipboard_get()
        except tk.TclError:
            # An empty clipboard raises TclError on most platforms.
            current = None
        if current == self._copied_value:
            self._widget.clipboard_clear()
            # Append empty string so some platforms register the clear.
            self._widget.clipboard_append("")
        self._copied_value = None
        self._pending_after = None
        if on_clear is not None:
            on_clear()

    def _cancel_pending(self) -> None:
        if self._pending_after is not None:
            # A stale Tk "after" id is harmless to cancel; ignore failures.
            with contextlib.suppress(tk.TclError):
                self._widget.after_cancel(self._pending_after)
            self._pending_after = None
