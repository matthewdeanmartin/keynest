"""Middle panel: edit the selected secret map and its key/value grid."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, simpledialog, ttk

from keynest.model import SecretMap, key_warning
from keynest.services import value_tools

MASK = "•" * 8  # eight bullet characters


class SecretEditor(ttk.Frame):
    """Displays and edits one :class:`~keynest.model.SecretMap`."""

    def __init__(
        self,
        parent: tk.Misc,
        on_save: Callable[[SecretMap], None],
        on_copy_value: Callable[[str, str], None],
    ) -> None:
        """Create the editor.

        Args:
            parent: Parent widget.
            on_save: Callback invoked with the edited map when the user saves.
            on_copy_value: Callback ``(key, value)`` for per-row copy.
        """
        super().__init__(parent, padding=8)
        self._on_save = on_save
        self._on_copy_value = on_copy_value
        self._map: SecretMap | None = None
        self._revealed: set[str] = set()

        header = ttk.Frame(self)
        header.pack(fill="x")
        self._title = ttk.Label(header, text="(no secret map selected)", font=("", 11, "bold"))
        self._title.pack(side="left")
        self._backend_label = ttk.Label(header, text="")
        self._backend_label.pack(side="right")

        meta = ttk.Frame(self)
        meta.pack(fill="x", pady=(6, 4))
        ttk.Label(meta, text="Description:").grid(row=0, column=0, sticky="w")
        self._desc_var = tk.StringVar()
        ttk.Entry(meta, textvariable=self._desc_var).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Label(meta, text="Tags:").grid(row=1, column=0, sticky="w")
        self._tags_var = tk.StringVar()
        ttk.Entry(meta, textvariable=self._tags_var).grid(row=1, column=1, sticky="ew", padx=4)
        meta.columnconfigure(1, weight=1)

        columns = ("key", "value", "kind")
        self._tree = ttk.Treeview(self, columns=columns, show="headings", height=10)
        self._tree.heading("key", text="KEY")
        self._tree.heading("value", text="VALUE")
        self._tree.heading("kind", text="KIND")
        self._tree.column("key", width=180)
        self._tree.column("value", width=260)
        self._tree.column("kind", width=80, anchor="center")
        self._tree.pack(fill="both", expand=True, pady=4)
        self._tree.bind("<Double-1>", lambda _e: self._toggle_reveal())

        controls = ttk.Frame(self)
        controls.pack(fill="x", pady=(4, 0))
        for text, command in (
            ("Add key", self._add_key),
            ("Edit value", self._edit_value),
            ("Rename key", self._rename_key),
            ("Delete key", self._delete_key),
            ("Reveal", self._toggle_reveal),
            ("Copy value", self._copy_value),
            ("Generate", self._generate_value),
            ("Save", self._save),
        ):
            ttk.Button(controls, text=text, command=command).pack(side="left", padx=2)

    # -- public API ----------------------------------------------------------

    def load(self, secret_map: SecretMap | None) -> None:
        """Display ``secret_map`` (or clear the panel when ``None``)."""
        self._map = secret_map
        self._revealed.clear()
        if secret_map is None:
            self._title.configure(text="(no secret map selected)")
            self._backend_label.configure(text="")
            self._desc_var.set("")
            self._tags_var.set("")
            self._refresh_rows()
            return
        self._title.configure(text=secret_map.path)
        self._backend_label.configure(text=secret_map.backend)
        self._desc_var.set(secret_map.description)
        self._tags_var.set(", ".join(secret_map.tags))
        self._refresh_rows()

    # -- internals -----------------------------------------------------------

    def _refresh_rows(self) -> None:
        self._tree.delete(*self._tree.get_children())
        if self._map is None:
            return
        for key in self._map.keys:
            raw = self._map.values[key]
            shown = str(raw) if key in self._revealed else MASK
            kind = "config" if not self._map.is_secret_key(key) else "secret"
            self._tree.insert("", "end", iid=key, values=(key, shown, kind))

    def _selected_key(self) -> str | None:
        selection = self._tree.selection()
        return selection[0] if selection else None

    def _require_map(self) -> SecretMap | None:
        if self._map is None:
            messagebox.showinfo("No selection", "Select or create a secret map first.")
        return self._map

    def _add_key(self) -> None:
        if (secret_map := self._require_map()) is None:
            return
        key = simpledialog.askstring("Add key", "Key name:", parent=self)
        if not key:
            return
        warning = key_warning(key)
        if warning and not messagebox.askyesno("Key name warning", f"{warning}\n\nAdd anyway?"):
            return
        value = simpledialog.askstring("Add key", f"Value for {key}:", parent=self) or ""
        secret_map.values[key] = value
        self._refresh_rows()

    def _edit_value(self) -> None:
        if (secret_map := self._require_map()) is None:
            return
        key = self._selected_key()
        if key is None:
            return
        current = str(secret_map.values.get(key, ""))
        new = simpledialog.askstring("Edit value", f"Value for {key}:", initialvalue=current, parent=self)
        if new is not None:
            secret_map.values[key] = new
            self._refresh_rows()

    def _rename_key(self) -> None:
        if (secret_map := self._require_map()) is None:
            return
        key = self._selected_key()
        if key is None:
            return
        new = simpledialog.askstring("Rename key", "New key name:", initialvalue=key, parent=self)
        if not new or new == key:
            return
        secret_map.values[new] = secret_map.values.pop(key)
        self._refresh_rows()

    def _delete_key(self) -> None:
        if (secret_map := self._require_map()) is None:
            return
        key = self._selected_key()
        if key is None:
            return
        if messagebox.askyesno("Delete key", f"Delete key {key!r}?"):
            secret_map.values.pop(key, None)
            self._refresh_rows()

    def _toggle_reveal(self) -> None:
        key = self._selected_key()
        if key is None:
            return
        if key in self._revealed:
            self._revealed.discard(key)
        else:
            self._revealed.add(key)
        self._refresh_rows()

    def _copy_value(self) -> None:
        if (secret_map := self._require_map()) is None:
            return
        key = self._selected_key()
        if key is None:
            return
        self._on_copy_value(key, str(secret_map.values.get(key, "")))

    def _generate_value(self) -> None:
        if (secret_map := self._require_map()) is None:
            return
        key = self._selected_key()
        if key is None:
            messagebox.showinfo("Generate", "Select a key to fill with a generated value.")
            return
        secret_map.values[key] = value_tools.generate_password()
        self._revealed.add(key)
        self._refresh_rows()

    def _save(self) -> None:
        if (secret_map := self._require_map()) is None:
            return
        secret_map.description = self._desc_var.get().strip()
        secret_map.tags = [t.strip() for t in self._tags_var.get().split(",") if t.strip()]
        self._on_save(secret_map)
