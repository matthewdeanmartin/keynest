"""Reusable Tkinter dialogs: scrolled text, code viewer, and warned exports."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from keynest.services.codegen import Snippet
from keynest.ui.geometry import center_window


class TextDialog(tk.Toplevel):
    """A modal dialog showing read-only, scrollable text with a Copy button.

    By default the text *wraps* at word boundaries, which suits prose (help and
    notes). Pass ``wrap=False`` for content where horizontal layout matters
    (e.g. code or aligned tables), which adds a horizontal scrollbar instead.
    """

    def __init__(self, parent: tk.Misc, title: str, content: str, *, wrap: bool = True) -> None:
        """Show ``content`` under ``title`` in a modal window."""
        super().__init__(parent)
        self.title(title)
        center_window(self, 680, 460)
        self.transient(parent)  # type: ignore[call-overload]  # ty: ignore[no-matching-overload]

        text = tk.Text(self, wrap="word" if wrap else "none", font=("Consolas", 10))
        text.insert("1.0", content)
        text.configure(state="disabled")

        yscroll = ttk.Scrollbar(self, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=yscroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        if not wrap:
            xscroll = ttk.Scrollbar(self, orient="horizontal", command=text.xview)
            text.configure(xscrollcommand=xscroll.set)
            xscroll.grid(row=1, column=0, sticky="ew")

        buttons = ttk.Frame(self)
        buttons.grid(row=2, column=0, columnspan=2, sticky="e", padx=8, pady=6)
        ttk.Button(buttons, text="Copy", command=lambda: self._copy(content)).pack(side="left", padx=4)
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="left", padx=4)

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.grab_set()

    def _copy(self, content: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(content)


class CodeViewerDialog(tk.Toplevel):
    """A dialog with a snippet picker on the left and the code on the right."""

    def __init__(self, parent: tk.Misc, snippets: list[Snippet]) -> None:
        """Show generated code ``snippets`` (a list of ``codegen.Snippet``)."""
        super().__init__(parent)
        self.title("Generate code")
        center_window(self, 820, 520)
        self.transient(parent)  # type: ignore[call-overload]  # ty: ignore[no-matching-overload]
        self._snippets = snippets

        listbox = tk.Listbox(self, exportselection=False, width=34)
        for snippet in snippets:
            listbox.insert("end", snippet.title)
        listbox.grid(row=0, column=0, sticky="ns", padx=(8, 4), pady=8)
        listbox.bind("<<ListboxSelect>>", self._on_select)
        self._listbox = listbox

        self._text = tk.Text(self, wrap="none", font=("Consolas", 10))
        self._text.grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=8)

        buttons = ttk.Frame(self)
        buttons.grid(row=1, column=0, columnspan=2, sticky="e", padx=8, pady=(0, 8))
        ttk.Button(buttons, text="Copy snippet", command=self._copy).pack(side="left", padx=4)
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="left", padx=4)

        self.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        if snippets:
            listbox.selection_set(0)
            self._show(0)
        self.grab_set()

    def _on_select(self, _event: object) -> None:
        selection = self._listbox.curselection()
        if selection:
            self._show(selection[0])

    def _show(self, index: int) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.insert("1.0", self._snippets[index].code)
        self._text.configure(state="disabled")

    def _copy(self) -> None:
        selection = self._listbox.curselection()
        if selection:
            self.clipboard_clear()
            self.clipboard_append(self._snippets[selection[0]].code)
