"""Right panel: usage actions that steer toward safe paths."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk


class ActionsPanel(ttk.Frame):
    """A vertical stack of action buttons for the selected secret map."""

    def __init__(self, parent: tk.Misc, actions: dict[str, Callable[[], None]]) -> None:
        """Create the panel from an ordered ``label -> callback`` mapping."""
        super().__init__(parent, padding=8)
        ttk.Label(self, text="Actions", font=("", 11, "bold")).pack(anchor="w", pady=(0, 6))

        # Group the recommended, safe paths visually at the top.
        for label, command in actions.items():
            if label == "---":
                ttk.Separator(self, orient="horizontal").pack(fill="x", pady=6)
                continue
            ttk.Button(self, text=label, command=command).pack(fill="x", pady=2)

        ttk.Label(
            self,
            text=("Prefer 'Run command' and 'Generate code'.\n" "Copy and Export touch shared OS state."),
            wraplength=170,
            foreground="#555",
            justify="left",
        ).pack(anchor="w", pady=(10, 0))
