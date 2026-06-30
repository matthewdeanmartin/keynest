"""Integration tests for the Tk clipboard helper using a real hidden root."""

from __future__ import annotations

from keynest.services.clipboard import DEFAULT_CLEAR_SECONDS, ClipboardManager


def test_copy_places_value_on_clipboard(tk_root):
    mgr = ClipboardManager(tk_root, clear_seconds=30)
    mgr.copy("hunter2")
    assert tk_root.clipboard_get() == "hunter2"


def _clipboard_or_empty(root) -> str:
    """Return the clipboard text, or "" if the clipboard is empty/unset."""
    import tkinter as tk

    try:
        text: str = root.clipboard_get()
        return text
    except tk.TclError:
        return ""


def test_clear_now_empties_clipboard(tk_root):
    mgr = ClipboardManager(tk_root, clear_seconds=30)
    mgr.copy("secret")
    mgr.clear_now()
    # The secret must be gone (cleared to empty string on platforms like Windows).
    assert _clipboard_or_empty(tk_root) == ""


def test_auto_clear_fires_after_timeout(tk_root):
    cleared = []
    mgr = ClipboardManager(tk_root, clear_seconds=0)  # 0s -> fires on next event loop
    mgr.copy("temp", on_clear=lambda: cleared.append(True))
    tk_root.update()  # flush the scheduled after(0, ...)
    assert cleared == [True]
    assert _clipboard_or_empty(tk_root) == ""


def test_auto_clear_preserves_value_copied_afterwards(tk_root):
    mgr = ClipboardManager(tk_root, clear_seconds=0)
    mgr.copy("ours")
    # User copies something else before the timer fires.
    tk_root.clipboard_clear()
    tk_root.clipboard_append("theirs")
    tk_root.update()  # auto-clear runs but must not stomp "theirs"
    assert tk_root.clipboard_get() == "theirs"


def test_second_copy_cancels_first_timer(tk_root):
    fired = []
    mgr = ClipboardManager(tk_root, clear_seconds=0)
    mgr.copy("first", on_clear=lambda: fired.append("first"))
    mgr.copy("second", on_clear=lambda: fired.append("second"))
    tk_root.update()
    # Only the second timer should remain active.
    assert "first" not in fired


def test_default_clear_seconds_constant():
    assert DEFAULT_CLEAR_SECONDS == 30
