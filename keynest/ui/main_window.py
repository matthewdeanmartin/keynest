"""The keynest main window: a three-panel secret workbench."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from keynest.backends.base import BackendError, SecretBackend
from keynest.backends.registry import get_backend
from keynest.model import BackendId, SecretMap, SecretMapRef, parse_path
from keynest.services import codegen, diagnostics, maptools
from keynest.services.audit import AuditLog
from keynest.services.aws_policy import generate_policy_json
from keynest.services.clipboard import CLIPBOARD_WARNING, ClipboardManager
from keynest.services.dotenv_parser import parse_dotenv_file, serialize_dotenv
from keynest.services.index_store import IndexStore
from keynest.ui.actions_panel import ActionsPanel
from keynest.ui.aws_wizard import AwsWizardDialog
from keynest.ui.dialogs import CodeViewerDialog, TextDialog
from keynest.ui.folder_panel import FolderPanel
from keynest.ui.quick_dialogs import PasteEnvDialog, QuickAddPasswordDialog
from keynest.ui.secret_editor import SecretEditor

SECURITY_NOTE = (
    "keynest protects against accidental commits, plaintext files, and casual "
    "shoulder-surfing. It does NOT protect against malware running as you, a "
    "compromised Python process, memory scraping, or AWS identity compromise."
)

KEYRING_LISTING_NOTE = (
    "keynest can only LIST secret maps it created itself.\n\n"
    "Operating-system credential stores (Windows Credential Manager, macOS "
    "Keychain, Linux Secret Service) do not offer a portable way to enumerate "
    "all entries. So keynest keeps its own non-secret index of what it has "
    "stored, at ~/.devsecrets/index.json (override with DEVSECRETS_HOME).\n\n"
    "Consequences:\n"
    "  - Secrets created by OTHER apps, or directly via keyring/keychain, will "
    "not appear here. keynest does not know their service/username, and the OS "
    "will not tell it.\n"
    "  - If the index file is missing or points elsewhere, your secrets are "
    "still safely IN the OS store, just not listed. Re-create the map with the "
    "same folder/name to re-index it (the value will be overwritten).\n\n"
    "Use 'Quick add password' or 'Paste .env' to add entries that keynest will "
    "track."
)


class MainWindow(tk.Tk):
    """Top-level application window."""

    def __init__(self) -> None:
        """Build the menu, three panels, and load the OS keyring backend."""
        super().__init__()
        self.title("keynest — Developer Secret Workbench")
        self.geometry("1024x600")

        self._backend_filter: BackendId | None = None
        self._current_map: SecretMap | None = None
        self._clipboard = ClipboardManager(self)

        self._build_menu()
        self._build_toolbar()

        paned = ttk.Panedwindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        self._folder_panel = FolderPanel(
            paned,
            on_select_map=self._select_map,
            on_new_map=self._new_map,
            on_backend_change=self._change_backend_filter,
            on_delete_map=self._delete_map,
            on_rename_map=self._rename_map,
            on_duplicate_map=self._duplicate_map,
        )
        self._editor = SecretEditor(paned, on_save=self._save_map, on_copy_value=self._copy_value)
        self._actions = self._build_actions(paned)

        paned.add(self._folder_panel, weight=1)
        paned.add(self._editor, weight=3)
        paned.add(self._actions, weight=1)

        self._status = ttk.Label(self, text="Ready", anchor="w", relief="sunken")
        self._status.pack(fill="x", side="bottom")

        self.refresh()

    # -- backend access ------------------------------------------------------

    def _backends_to_query(self) -> list[BackendId]:
        if self._backend_filter is None:
            # Only the OS keyring is queried by default; AWS requires creds and is
            # opt-in via the backend filter to avoid slow/failed calls on startup.
            return ["os-keyring"]
        return [self._backend_filter]

    def _backend_for(self, backend_id: BackendId) -> SecretBackend:
        return get_backend(backend_id)

    # -- menu ----------------------------------------------------------------

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Quick add password...", command=self._quick_add_password)
        file_menu.add_command(label="Paste .env...", command=self._paste_env)
        file_menu.add_separator()
        file_menu.add_command(label="New secret map", command=lambda: self._new_map("default"))
        file_menu.add_command(label="Refresh", command=self.refresh)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self._quit)
        menubar.add_cascade(label="File", menu=file_menu)

        backend_menu = tk.Menu(menubar, tearoff=0)
        backend_menu.add_command(label="Health check", command=self._health_check)
        backend_menu.add_command(label="AWS setup wizard...", command=self._aws_wizard)
        backend_menu.add_command(label="Generate AWS IAM policy", command=self._aws_policy)
        menubar.add_cascade(label="Backend", menu=backend_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Import .env", command=self._import_env)
        tools_menu.add_command(label="Export .env (less safe)", command=self._export_env)
        tools_menu.add_separator()
        tools_menu.add_command(label="Lint current map", command=self._lint_map)
        tools_menu.add_command(label="Diff maps...", command=self._diff_maps)
        tools_menu.add_command(label="Redacted export (current)", command=self._redacted_export)
        tools_menu.add_command(label="Stale maps...", command=self._stale_maps)
        tools_menu.add_separator()
        tools_menu.add_command(label="Recent activity", command=self._recent_activity)
        tools_menu.add_command(label="Diagnostics", command=self._show_diagnostics)
        tools_menu.add_command(label="Back up index", command=self._backup_index)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        code_menu = tk.Menu(menubar, tearoff=0)
        code_menu.add_command(label="Generate code", command=self._generate_code)
        menubar.add_cascade(label="Code", menu=code_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Why is my list empty?", command=self._show_keyring_help)
        help_menu.add_command(label="Security posture", command=self._show_security)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menubar)

    def _build_toolbar(self) -> None:
        """A thin toolbar with the most common, lowest-friction actions."""
        toolbar = ttk.Frame(self, padding=(6, 4))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="+ Quick add password", command=self._quick_add_password).pack(side="left")
        ttk.Button(toolbar, text="Paste .env", command=self._paste_env).pack(side="left", padx=6)
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(toolbar, text="New map", command=lambda: self._new_map("default")).pack(side="left")
        ttk.Button(toolbar, text="Refresh", command=self.refresh).pack(side="left", padx=6)

    def _build_actions(self, parent: tk.Misc) -> ActionsPanel:
        actions = {
            "Run command with secrets": self._run_command,
            "Generate code": self._generate_code,
            "---": lambda: None,
            "Copy selected value": self._copy_selected_value,
            "Generate AWS IAM policy": self._aws_policy,
            "Import .env": self._import_env,
            "Export .env (less safe)": self._export_env,
            "Health check": self._health_check,
        }
        return ActionsPanel(parent, actions)

    # -- data refresh --------------------------------------------------------

    def refresh(self) -> None:
        """Reload folders and secret-map references from the active backend(s)."""
        folders: set[str] = {"default"}
        refs: list[SecretMapRef] = []
        for backend_id in self._backends_to_query():
            try:
                backend = self._backend_for(backend_id)
                for folder in backend.list_folders():
                    folders.add(folder)
                refs.extend(backend.list_secret_maps())
            except BackendError as exc:
                self._set_status(f"{backend_id}: {exc}")
        self._folder_panel.set_data(sorted(folders), refs)
        if not refs:
            self._set_status(
                "No secret maps tracked yet. Use 'Quick add password' or 'Paste .env'. "
                "(keynest only lists what it created — see Help > Why is my list empty?)"
            )

    def _change_backend_filter(self, backend_id: BackendId | None) -> None:
        self._backend_filter = backend_id
        self.refresh()

    # -- selection / save ----------------------------------------------------

    def _select_map(self, ref: SecretMapRef) -> None:
        try:
            backend = self._backend_for(ref.backend)
            self._current_map = backend.get_secret_map(ref.folder, ref.name)
            self._editor.load(self._current_map)
            self._set_status(f"Loaded {ref.path}")
        except BackendError as exc:
            messagebox.showerror("Load failed", str(exc))

    def _new_map(self, folder: str) -> None:
        name = simpledialog.askstring("New secret map", "Name:", parent=self)
        if not name:
            return
        backend_id = self._backend_filter or "os-keyring"
        new_map = SecretMap(backend=backend_id, folder=folder, name=name)
        self._current_map = new_map
        self._editor.load(new_map)
        self._set_status(f"New map {new_map.path} (add keys, then Save)")

    def _active_backend_id(self) -> BackendId:
        """The backend to create new maps in (the filter, else OS keyring)."""
        return self._backend_filter or "os-keyring"

    def _on_quick_saved(self, ref: SecretMapRef) -> None:
        """Refresh and select a map produced by a quick dialog."""
        self.refresh()
        self._select_map(ref)

    def _quick_add_password(self) -> None:
        backend_id = self._active_backend_id()
        QuickAddPasswordDialog(self, self._backend_for(backend_id), backend_id, self._on_quick_saved)

    def _paste_env(self) -> None:
        backend_id = self._active_backend_id()
        folder = self._folder_panel.selected_folder() or "default"
        PasteEnvDialog(
            self,
            self._backend_for(backend_id),
            backend_id,
            self._on_quick_saved,
            default_path=f"{folder}/pasted",
        )

    def _show_keyring_help(self) -> None:
        TextDialog(self, "Why is my list empty?", KEYRING_LISTING_NOTE)

    def _save_map(self, secret_map: SecretMap) -> None:
        try:
            backend = self._backend_for(secret_map.backend)
            backend.put_secret_map(secret_map)
            self._set_status(f"Saved {secret_map.path}")
            self.refresh()
        except BackendError as exc:
            messagebox.showerror("Save failed", str(exc))

    def _delete_map(self, ref: SecretMapRef) -> None:
        if not messagebox.askyesno("Delete secret map", f"Delete {ref.path}? This cannot be undone."):
            return
        try:
            self._backend_for(ref.backend).delete_secret_map(ref.folder, ref.name)
            if self._current_map is not None and self._current_map.ref == ref:
                self._current_map = None
                self._editor.load(None)
            self._set_status(f"Deleted {ref.path}")
            self.refresh()
        except BackendError as exc:
            messagebox.showerror("Delete failed", str(exc))

    def _rename_map(self, ref: SecretMapRef) -> None:
        new_folder = simpledialog.askstring("Rename / move", "Folder:", initialvalue=ref.folder, parent=self)
        if new_folder is None:
            return
        new_name = simpledialog.askstring("Rename / move", "Name:", initialvalue=ref.name, parent=self)
        if not new_name:
            return
        new_ref = SecretMapRef(ref.backend, new_folder, new_name)
        if new_ref == ref:
            return
        try:
            self._backend_for(ref.backend).rename_secret_map(ref, new_ref)
            self._set_status(f"Renamed {ref.path} to {new_ref.path}")
            self.refresh()
            self._select_map(new_ref)
        except BackendError as exc:
            messagebox.showerror("Rename failed", str(exc))

    def _duplicate_map(self, ref: SecretMapRef) -> None:
        new_name = simpledialog.askstring(
            "Duplicate secret map", "New name:", initialvalue=f"{ref.name}-copy", parent=self
        )
        if not new_name:
            return
        try:
            backend = self._backend_for(ref.backend)
            source = backend.get_secret_map(ref.folder, ref.name)
            copy = maptools.duplicate_map(source, new_name)
            backend.put_secret_map(copy)
            self._set_status(f"Duplicated {ref.path} to {copy.path}")
            self.refresh()
            self._select_map(copy.ref)
        except BackendError as exc:
            messagebox.showerror("Duplicate failed", str(exc))

    # -- actions -------------------------------------------------------------

    def _require_current(self) -> SecretMap | None:
        if self._current_map is None:
            messagebox.showinfo("No selection", "Select or create a secret map first.")
        return self._current_map

    def _copy_value(self, key: str, value: str) -> None:
        self._clipboard.copy(value)
        self._set_status(f"Copied {key}; clears in {self._clipboard.clear_seconds}s. {CLIPBOARD_WARNING}")

    def _copy_selected_value(self) -> None:
        if (secret_map := self._require_current()) is None:
            return
        if not secret_map.values:
            messagebox.showinfo("Copy", "This map has no keys.")
            return
        key = sorted(secret_map.values)[0]
        self._copy_value(key, str(secret_map.values[key]))

    def _run_command(self) -> None:
        if (secret_map := self._require_current()) is None:
            return
        path = f"{secret_map.folder}/{secret_map.name}"
        TextDialog(
            self,
            "Run command with secrets",
            "Run from your terminal so secrets stay in the child process only:\n\n"
            f"    keynest run {path} -- python app.py\n\n"
            "This injects the map into the subprocess environment without writing\n"
            "secrets to disk or printing them.",
        )

    def _generate_code(self) -> None:
        if (secret_map := self._require_current()) is None:
            return
        CodeViewerDialog(self, codegen.all_snippets(secret_map))

    def _aws_policy(self) -> None:
        account = simpledialog.askstring("AWS IAM policy", "Account id:", parent=self) or "<account-id>"
        region = simpledialog.askstring("AWS IAM policy", "Region:", parent=self) or "<region>"
        folder = self._folder_panel.selected_folder()
        policy = generate_policy_json(region, account, folder=folder)
        TextDialog(self, "AWS IAM policy", policy)

    def _aws_wizard(self) -> None:
        AwsWizardDialog(self)

    def _import_env(self) -> None:
        if (secret_map := self._require_current()) is None:
            return
        path = filedialog.askopenfilename(title="Select .env file")
        if not path:
            return
        result = parse_dotenv_file(path)
        if result.warnings:
            messagebox.showwarning("Import warnings", "\n".join(result.warnings[:20]))
        secret_map.values.update(result.values)
        self._editor.load(secret_map)
        self._set_status(f"Imported {len(result.values)} key(s). Review, then Save.")

    def _export_env(self) -> None:
        if (secret_map := self._require_current()) is None:
            return
        proceed = messagebox.askyesno(
            "Export .env (less safe)",
            "Exporting writes plaintext secrets to disk.\n\n"
            "Prefer 'Run command with secrets' or 'Generate code'.\n\n"
            "Export anyway?",
            icon="warning",
            default="no",
        )
        if not proceed:
            return
        path = filedialog.asksaveasfilename(title="Export to .env", defaultextension=".env")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(serialize_dotenv(secret_map.values))
        self._set_status(f"Exported plaintext to {path}")

    def _run_path(self, secret_map: SecretMap) -> str:
        return f"{secret_map.folder}/{secret_map.name}"

    # -- Phase 5 report tools ------------------------------------------------

    def _lint_map(self) -> None:
        if (secret_map := self._require_current()) is None:
            return
        findings = maptools.lint_map(secret_map)
        if not findings:
            TextDialog(self, "Lint", f"{secret_map.path}: clean — no issues found.")
            return
        lines = [f"{f.key}: {f.message}" for f in findings]
        TextDialog(self, f"Lint — {secret_map.path}", "\n".join(lines))

    def _redacted_export(self) -> None:
        if (secret_map := self._require_current()) is None:
            return
        TextDialog(self, f"Redacted export — {secret_map.path}", maptools.export_redacted_json(secret_map))

    def _diff_maps(self) -> None:
        if (left := self._require_current()) is None:
            return
        other = simpledialog.askstring("Diff maps", "Compare against (folder/name):", parent=self)
        if not other:
            return
        try:
            folder, name = parse_path(other)
            right = self._backend_for(left.backend).get_secret_map(folder, name)
        except (BackendError, ValueError) as exc:
            messagebox.showerror("Diff failed", str(exc))
            return
        diff = maptools.diff_maps(left, right)
        lines = [f"{left.path} -> {right.path}", ""]
        lines += [f"  + {k}" for k in diff.added]
        lines += [f"  - {k}" for k in diff.removed]
        lines += [f"  ~ {k}" for k in diff.changed]
        if not diff.has_changes:
            lines.append("  (identical keys and values)")
        TextDialog(self, "Diff maps", "\n".join(lines))

    def _stale_maps(self) -> None:
        days = simpledialog.askinteger(
            "Stale maps", "Staleness threshold (days):", initialvalue=90, minvalue=0, parent=self
        )
        if days is None:
            return
        index = IndexStore()
        lines = []
        for item in sorted(index.items(), key=lambda i: (i.folder, i.name)):
            if maptools.is_stale(item.updated_at, stale_days=days):
                age = maptools.age_in_days(item.updated_at)
                age_text = f"{age:.0f}d" if age is not None else "unknown"
                lines.append(f"/{item.folder}/{item.name}  (age: {age_text}, updated: {item.updated_at or 'never'})")
        body = "\n".join(lines) if lines else f"No maps older than {days} days."
        TextDialog(self, "Stale maps", body)

    def _recent_activity(self) -> None:
        events = AuditLog().events(limit=50)
        if not events:
            TextDialog(self, "Recent activity", "(no audit events)")
            return
        lines = [
            f"{e.timestamp}  {e.action:<12} /{e.folder}/{e.name}{(' ' + e.key) if e.key else ''}  [{e.backend}]"
            for e in events
        ]
        TextDialog(self, "Recent activity", "\n".join(lines))

    def _show_diagnostics(self) -> None:
        TextDialog(self, "Diagnostics", "\n".join(diagnostics.collect().as_lines()))

    def _backup_index(self) -> None:
        destination = IndexStore().backup()
        if destination is None:
            self._set_status("No index file to back up.")
            messagebox.showinfo("Back up index", "There is no index file to back up yet.")
            return
        self._set_status(f"Backed up index to {destination}")
        messagebox.showinfo("Back up index", f"Backed up index to:\n{destination}")

    def _health_check(self) -> None:
        lines = []
        for backend_id in ("os-keyring",):
            status = self._backend_for(backend_id).test_connection()
            marker = "OK" if status.ok else "FAIL"
            lines.append(f"[{marker}] {backend_id}: {status.detail}")
        TextDialog(self, "Health check", "\n".join(lines))

    def _show_security(self) -> None:
        TextDialog(self, "Security posture", SECURITY_NOTE)

    # -- misc ----------------------------------------------------------------

    def _set_status(self, text: str) -> None:
        self._status.configure(text=text)

    def _quit(self) -> None:
        self._clipboard.clear_now()
        self.destroy()


def run() -> None:
    """Launch the keynest GUI."""
    app = MainWindow()
    app.mainloop()
