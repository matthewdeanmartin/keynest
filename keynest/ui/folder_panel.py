"""Left panel: folders, the secret-map list, and the backend filter."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from keynest.model import BackendId, SecretMapRef

BACKEND_CHOICES = ["All", "OS keyring", "AWS Secrets Manager"]
_LABEL_TO_ID: dict[str, BackendId] = {
    "OS keyring": "os-keyring",
    "AWS Secrets Manager": "aws-secrets-manager",
}


class FolderPanel(ttk.Frame):
    """Folder list, secret-map list, and backend filter."""

    def __init__(
        self,
        parent: tk.Misc,
        on_select_map: Callable[[SecretMapRef], None],
        on_new_map: Callable[[str], None],
        on_backend_change: Callable[[BackendId | None], None],
        on_delete_map: Callable[[SecretMapRef], None],
        on_rename_map: Callable[[SecretMapRef], None],
        on_duplicate_map: Callable[[SecretMapRef], None],
    ) -> None:
        """Create the panel.

        Args:
            parent: Parent widget.
            on_select_map: Called with a ref when a secret map is selected.
            on_new_map: Called with the active folder name to create a new map.
            on_backend_change: Called with a backend id (or ``None`` for All).
            on_delete_map: Called with the selected ref to delete a map.
            on_rename_map: Called with the selected ref to rename/move a map.
            on_duplicate_map: Called with the selected ref to duplicate a map.
        """
        super().__init__(parent, padding=6)
        self._on_select_map = on_select_map
        self._on_new_map = on_new_map
        self._on_backend_change = on_backend_change
        self._on_delete_map = on_delete_map
        self._on_rename_map = on_rename_map
        self._on_duplicate_map = on_duplicate_map
        self._refs: list[SecretMapRef] = []
        self._visible_refs: list[SecretMapRef] = []

        ttk.Label(self, text="Backend:").pack(anchor="w")
        self._backend_var = tk.StringVar(value=BACKEND_CHOICES[0])
        backend_box = ttk.Combobox(self, textvariable=self._backend_var, values=BACKEND_CHOICES, state="readonly")
        backend_box.pack(fill="x", pady=(0, 6))
        backend_box.bind("<<ComboboxSelected>>", lambda _e: self._backend_changed())

        ttk.Label(self, text="Folders").pack(anchor="w")
        self._folders = tk.Listbox(self, exportselection=False, height=8)
        self._folders.pack(fill="both", expand=False)
        self._folders.bind("<<ListboxSelect>>", lambda _e: self._refresh_maps())

        ttk.Label(self, text="Secret Maps").pack(anchor="w", pady=(6, 0))
        self._maps = tk.Listbox(self, exportselection=False, height=12)
        self._maps.pack(fill="both", expand=True)
        self._maps.bind("<<ListboxSelect>>", lambda _e: self._map_selected())
        # Right-click selects the row under the cursor, then shows the context menu.
        self._maps.bind("<Button-3>", self._show_context_menu)

        self._context_menu = tk.Menu(self, tearoff=0)
        self._context_menu.add_command(label="Rename / move...", command=self._rename_map)
        self._context_menu.add_command(label="Duplicate...", command=self._duplicate_map)
        self._context_menu.add_separator()
        self._context_menu.add_command(label="Delete", command=self._delete_map)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=(6, 0))
        ttk.Button(buttons, text="New map", command=self._new_map).pack(side="left", padx=2)
        ttk.Button(buttons, text="Rename...", command=self._rename_map).pack(side="left", padx=2)
        ttk.Button(buttons, text="Duplicate...", command=self._duplicate_map).pack(side="left", padx=2)
        ttk.Button(buttons, text="Delete", command=self._delete_map).pack(side="left", padx=2)

    # -- public API ----------------------------------------------------------

    def set_data(self, folders: list[str], refs: list[SecretMapRef]) -> None:
        """Populate the folder list and remember the available map refs."""
        self._refs = refs
        previous = self.selected_folder()
        self._folders.delete(0, "end")
        for folder in folders:
            self._folders.insert("end", folder)
        # Restore the prior folder selection if still present.
        if previous in folders:
            index = folders.index(previous)
        elif folders:
            index = 0
        else:
            index = None
        if index is not None:
            self._folders.selection_set(index)
        self._refresh_maps()

    def selected_folder(self) -> str | None:
        """Return the currently selected folder name, or ``None``."""
        selection = self._folders.curselection()
        if not selection:
            return None
        return self._folders.get(selection[0])

    def selected_ref(self) -> SecretMapRef | None:
        """Return the currently selected secret-map ref, or ``None``."""
        selection = self._maps.curselection()
        if not selection:
            return None
        return self._visible_refs[selection[0]]

    def active_backend_id(self) -> BackendId | None:
        """Return the selected backend id, or ``None`` for All."""
        return _LABEL_TO_ID.get(self._backend_var.get())

    # -- internals -----------------------------------------------------------

    def _backend_changed(self) -> None:
        self._on_backend_change(self.active_backend_id())

    def _refresh_maps(self) -> None:
        folder = self.selected_folder()
        self._maps.delete(0, "end")
        self._visible_refs = [r for r in self._refs if folder is None or r.folder == folder]
        for ref in self._visible_refs:
            self._maps.insert("end", ref.name)

    def _map_selected(self) -> None:
        selection = self._maps.curselection()
        if not selection:
            return
        ref = self._visible_refs[selection[0]]
        self._on_select_map(ref)

    def _new_map(self) -> None:
        folder = self.selected_folder() or "default"
        self._on_new_map(folder)

    def _show_context_menu(self, event: tk.Event) -> None:
        # Select the row under the pointer so the action targets it.
        index = self._maps.nearest(event.y)
        if index >= 0 and self._visible_refs:
            self._maps.selection_clear(0, "end")
            self._maps.selection_set(index)
            self._context_menu.tk_popup(event.x_root, event.y_root)

    def _delete_map(self) -> None:
        ref = self.selected_ref()
        if ref is not None:
            self._on_delete_map(ref)

    def _rename_map(self) -> None:
        ref = self.selected_ref()
        if ref is not None:
            self._on_rename_map(ref)

    def _duplicate_map(self) -> None:
        ref = self.selected_ref()
        if ref is not None:
            self._on_duplicate_map(ref)
