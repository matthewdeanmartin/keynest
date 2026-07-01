"""Left panel: folders, the secret-map list, and the backend filter."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from keynest.model import BackendId, RawCredential, SecretMapRef

BACKEND_CHOICES = ["All", "OS keyring", "AWS Secrets Manager"]
_LABEL_TO_ID: dict[str, BackendId] = {
    "OS keyring": "os-keyring",
    "AWS Secrets Manager": "aws-secrets-manager",
}

# Synthetic folder under which non-keynest OS credentials are grouped when the
# "show all" toggle is on. Parenthesized so it sorts and reads as non-editable.
RAW_FOLDER = "(os credentials)"
# Prefix marking a raw, read-only credential row in the maps list.
RAW_MARKER = "⊘ "


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
        on_select_raw: Callable[[RawCredential], None] | None = None,
        on_show_all_change: Callable[[bool], None] | None = None,
        on_folder_select: Callable[[str | None], None] | None = None,
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
            on_select_raw: Called with a raw credential when a read-only OS
                credential row is selected.
            on_show_all_change: Called with the new toggle state when the user
                flips "show all OS credentials".
        """
        super().__init__(parent, padding=6)
        self._on_select_map = on_select_map
        self._on_new_map = on_new_map
        self._on_backend_change = on_backend_change
        self._on_delete_map = on_delete_map
        self._on_rename_map = on_rename_map
        self._on_duplicate_map = on_duplicate_map
        self._on_select_raw = on_select_raw
        self._on_show_all_change = on_show_all_change
        self._on_folder_select = on_folder_select
        self._refs: list[SecretMapRef] = []
        self._raw: list[RawCredential] = []
        # Each visible map row maps 1:1 to an entry here: a SecretMapRef for a
        # keynest map, or a RawCredential for a read-only OS credential.
        self._visible_rows: list[SecretMapRef | RawCredential] = []

        ttk.Label(self, text="Backend:").pack(anchor="w")
        self._backend_var = tk.StringVar(value=BACKEND_CHOICES[0])
        backend_box = ttk.Combobox(self, textvariable=self._backend_var, values=BACKEND_CHOICES, state="readonly")
        backend_box.pack(fill="x", pady=(0, 6))
        backend_box.bind("<<ComboboxSelected>>", lambda _e: self._backend_changed())

        self._show_all_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self,
            text="Show all OS credentials (names only)",
            variable=self._show_all_var,
            command=self._show_all_changed,
        ).pack(anchor="w", pady=(0, 6))

        ttk.Label(self, text="Folders").pack(anchor="w")
        self._folders = tk.Listbox(self, exportselection=False, height=8)
        self._folders.pack(fill="both", expand=False)
        self._folders.bind("<<ListboxSelect>>", lambda _e: self._folder_selected())

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

    def set_data(
        self,
        folders: list[str],
        refs: list[SecretMapRef],
        raw: list[RawCredential] | None = None,
        select: str | None = None,
    ) -> None:
        """Populate the folder list and remember the available map refs.

        Args:
            folders: Folder names for keynest-managed maps.
            refs: Keynest-managed secret-map references.
            raw: Non-keynest OS credentials to show read-only (when the
                "show all" toggle is on). Grouped under :data:`RAW_FOLDER`.
            select: Folder to select if present, taking precedence over
                restoring the prior selection. Used to steer to a detected repo.
        """
        self._refs = refs
        self._raw = raw or []
        display_folders = list(folders)
        if self._raw and RAW_FOLDER not in display_folders:
            display_folders.append(RAW_FOLDER)
        previous = self.selected_folder()
        self._folders.delete(0, "end")
        for folder in display_folders:
            self._folders.insert("end", folder)
        folders = display_folders
        # Choose the selection: explicit `select` wins, then the prior folder,
        # then the first folder.
        if select is not None and select in folders:
            index = folders.index(select)
        elif previous is not None and previous in folders:
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
        """Return the currently selected *editable* secret-map ref, or ``None``.

        Raw OS credentials are read-only and are never returned here, so the
        rename/duplicate/delete actions cannot target them.
        """
        selection = self._maps.curselection()
        if not selection:
            return None
        row = self._visible_rows[selection[0]]
        return row if isinstance(row, SecretMapRef) else None

    def active_backend_id(self) -> BackendId | None:
        """Return the selected backend id, or ``None`` for All."""
        return _LABEL_TO_ID.get(self._backend_var.get())

    def show_all(self) -> bool:
        """Return whether the "show all OS credentials" toggle is on."""
        return self._show_all_var.get()

    def raw_credentials(self) -> list[RawCredential]:
        """Return the raw OS credentials currently held by the panel."""
        return list(self._raw)

    # -- internals -----------------------------------------------------------

    def _backend_changed(self) -> None:
        self._on_backend_change(self.active_backend_id())

    def _show_all_changed(self) -> None:
        if self._on_show_all_change is not None:
            self._on_show_all_change(self._show_all_var.get())

    def _folder_selected(self) -> None:
        self._refresh_maps()
        if self._on_folder_select is not None:
            self._on_folder_select(self.selected_folder())

    def _refresh_maps(self) -> None:
        folder = self.selected_folder()
        self._maps.delete(0, "end")
        rows: list[SecretMapRef | RawCredential] = []
        if folder == RAW_FOLDER:
            rows.extend(self._raw)
        else:
            rows.extend(r for r in self._refs if folder is None or r.folder == folder)
            # In the "All" view (no folder selected) also show raw creds inline.
            if folder is None:
                rows.extend(self._raw)
        self._visible_rows = rows
        for row in rows:
            if isinstance(row, RawCredential):
                self._maps.insert("end", f"{RAW_MARKER}{row.label}")
            else:
                self._maps.insert("end", row.name)

    def _map_selected(self) -> None:
        selection = self._maps.curselection()
        if not selection:
            return
        row = self._visible_rows[selection[0]]
        if isinstance(row, RawCredential):
            if self._on_select_raw is not None:
                self._on_select_raw(row)
        else:
            self._on_select_map(row)

    def _new_map(self) -> None:
        folder = self.selected_folder() or "default"
        self._on_new_map(folder)

    def _show_context_menu(self, event: tk.Event) -> None:
        # Select the row under the pointer so the action targets it.
        index = self._maps.nearest(event.y)
        if index < 0 or index >= len(self._visible_rows):
            return
        # Raw OS credentials are read-only; no rename/duplicate/delete menu.
        if isinstance(self._visible_rows[index], RawCredential):
            return
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
