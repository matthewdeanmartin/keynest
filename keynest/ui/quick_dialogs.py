"""Low-friction creation dialogs: quick single password, and bulk .env paste."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk

from keynest.backends.base import BackendError, SecretBackend
from keynest.model import BackendId, SecretMapRef
from keynest.services import quick, value_tools
from keynest.ui.geometry import center_window


class QuickAddPasswordDialog(tk.Toplevel):
    """Two-field dialog: a name and a value, saved as ``/default/<name>``.

    This is the fast path for "I just want to stash FOO=xyzzy" without choosing a
    folder or building a multi-key map. The value is stored under a single key.
    """

    def __init__(
        self,
        parent: tk.Misc,
        backend: SecretBackend,
        backend_id: BackendId,
        on_saved: Callable[[SecretMapRef], None],
        folder: str = "default",
    ) -> None:
        """Build the dialog.

        Args:
            parent: Parent widget.
            backend: Backend to persist into.
            backend_id: Backend id for the created map.
            on_saved: Called with the new map's ref after a successful save.
            folder: Destination folder for the created map (default ``default``).
        """
        super().__init__(parent)
        self.title("Quick add password")
        center_window(self, 420, 190)
        self.transient(parent)  # type: ignore[call-overload]  # ty: ignore[no-matching-overload]
        self._backend = backend
        self._backend_id = backend_id
        self._on_saved = on_saved
        self._folder = folder

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        ttk.Label(body, text="Name:").grid(row=0, column=0, sticky="w", pady=4)
        self._name_var = tk.StringVar()
        name_entry = ttk.Entry(body, textvariable=self._name_var, width=34)
        name_entry.grid(row=0, column=1, columnspan=2, sticky="ew", pady=4)

        ttk.Label(body, text="Value:").grid(row=1, column=0, sticky="w", pady=4)
        self._value_var = tk.StringVar()
        ttk.Entry(body, textvariable=self._value_var, width=34).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(body, text="Generate", command=self._generate).grid(row=1, column=2, padx=(4, 0))

        ttk.Label(
            body,
            text=f"Saved as /{self._folder}/<name> with a single key (VALUE).",
            foreground="#555",
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))

        buttons = ttk.Frame(body)
        buttons.grid(row=3, column=0, columnspan=3, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Save", command=self._save).pack(side="left", padx=4)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=4)

        body.columnconfigure(1, weight=1)
        name_entry.focus_set()
        self.bind("<Return>", lambda _e: self._save())
        self.grab_set()

    def _generate(self) -> None:
        self._value_var.set(value_tools.generate_password())

    def _save(self) -> None:
        name = self._name_var.get().strip()
        if not name:
            messagebox.showinfo("Quick add", "Please enter a name.")
            return
        try:
            secret_map = quick.quick_create_password(
                self._backend,
                name,
                self._value_var.get(),
                backend_id=self._backend_id,
                folder=self._folder,
            )
        except (BackendError, ValueError) as exc:
            messagebox.showerror("Quick add failed", str(exc))
            return
        self._on_saved(secret_map.ref)
        self.destroy()


class PasteEnvDialog(tk.Toplevel):
    """Paste many ``KEY=value`` lines at once and save them into one map."""

    def __init__(
        self,
        parent: tk.Misc,
        backend: SecretBackend,
        backend_id: BackendId,
        on_saved: Callable[[SecretMapRef], None],
        default_path: str = "default/pasted",
    ) -> None:
        """Build the dialog.

        Args:
            parent: Parent widget.
            backend: Backend to persist into.
            backend_id: Backend id for the created/updated map.
            on_saved: Called with the saved map's ref after a successful save.
            default_path: Prefilled ``folder/name`` target.
        """
        super().__init__(parent)
        self.title("Paste .env")
        center_window(self, 560, 460)
        self.transient(parent)  # type: ignore[call-overload]  # ty: ignore[no-matching-overload]
        self._backend = backend
        self._backend_id = backend_id
        self._on_saved = on_saved

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        target = ttk.Frame(body)
        target.pack(fill="x")
        ttk.Label(target, text="Save into (folder/name):").pack(side="left")
        self._path_var = tk.StringVar(value=default_path)
        ttk.Entry(target, textvariable=self._path_var, width=28).pack(side="left", padx=6)

        ttk.Label(body, text="Paste KEY=value lines (.env style):").pack(anchor="w", pady=(8, 2))
        self._text = tk.Text(body, height=14, font=("Consolas", 10), wrap="none")
        self._text.pack(fill="both", expand=True)

        self._status = ttk.Label(body, text="", foreground="#555", justify="left", wraplength=520)
        self._status.pack(anchor="w", pady=(6, 0))

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Preview", command=self._preview).pack(side="left", padx=2)
        ttk.Button(buttons, text="Save", command=self._save).pack(side="left", padx=2)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=2)

        self._text.focus_set()
        self.grab_set()

    def _preview(self) -> None:
        result = quick.preview_env(self._text.get("1.0", "end"))
        if not result.values:
            self._status.configure(text="No KEY=value pairs found yet.")
            return
        summary = f"{len(result.values)} key(s): {', '.join(sorted(result.values))}"
        if result.warnings:
            summary += "\nWarnings:\n  " + "\n  ".join(result.warnings[:10])
        self._status.configure(text=summary)

    def _save(self) -> None:
        try:
            secret_map, result = quick.bulk_set_from_env(
                self._backend, self._path_var.get(), self._text.get("1.0", "end"), backend_id=self._backend_id
            )
        except (BackendError, ValueError) as exc:
            messagebox.showerror("Paste .env failed", str(exc))
            return
        if result.warnings:
            messagebox.showwarning("Imported with warnings", "\n".join(result.warnings[:20]))
        self._on_saved(secret_map.ref)
        self.destroy()
