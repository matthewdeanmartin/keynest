"""Light integration tests for MainWindow and the AWS wizard dialog.

MainWindow is its own Tk root, so these construct it directly against the
in-memory keyring and isolated DEVSECRETS_HOME, drive the handler methods the
menus/toolbar/buttons bind to, and assert on backend state and widget output.
"""

from __future__ import annotations

import pytest

from keynest.backends.os_keyring import OsKeyringBackend
from keynest.model import SecretMap, SecretMapRef
from keynest.services import quick
from keynest.services.index_store import IndexStore


@pytest.fixture
def window(mem_keyring, devsecrets_home):
    """A live MainWindow over the in-memory keyring; destroyed on teardown."""
    import tkinter as tk

    from keynest.ui.main_window import MainWindow

    try:
        win = MainWindow()
    except tk.TclError as exc:  # pragma: no cover - headless without display
        pytest.skip(f"no Tk display available: {exc}")
    win.withdraw()
    try:
        yield win
    finally:
        try:
            win.update_idletasks()
            win.destroy()
        except tk.TclError:  # pragma: no cover
            pass


def _backend() -> OsKeyringBackend:
    return OsKeyringBackend(index=IndexStore())


def test_window_starts_empty_with_hint(window):
    # No maps yet -> status hint nudges toward quick add.
    assert "Quick add" in window._status.cget("text") or "empty" in window._status.cget("text").lower()


def test_refresh_lists_existing_map(window):
    quick.quick_create_password(_backend(), "github-token", "xyzzy")
    window.refresh()
    # The folder panel now shows the map under /default.
    window._folder_panel._maps.selection_clear(0, "end")
    names = list(window._folder_panel._maps.get(0, "end"))
    assert "github-token" in names


def test_select_map_loads_into_editor(window):
    quick.quick_create_password(_backend(), "db", "pw")
    window.refresh()
    window._select_map(SecretMapRef("os-keyring", "default", "db"))
    assert window._current_map is not None
    assert window._current_map.values == {"VALUE": "pw"}
    assert "/default/db" in window._editor._title.cget("text")


def test_save_map_persists(window):
    sm = SecretMap(backend="os-keyring", folder="app", name="dev", values={"A": "1"})
    window._save_map(sm)
    assert _backend().get_secret_map("app", "dev").values == {"A": "1"}


def test_delete_map_removes(window, monkeypatch):

    quick.quick_create_password(_backend(), "doomed", "x")
    window.refresh()
    monkeypatch.setattr("keynest.ui.main_window.messagebox.askyesno", lambda *a, **k: True)
    window._delete_map(SecretMapRef("os-keyring", "default", "doomed"))
    assert _backend().list_secret_maps() == []


def test_delete_map_cancelled_keeps_it(window, monkeypatch):

    quick.quick_create_password(_backend(), "keep", "x")
    window.refresh()
    monkeypatch.setattr("keynest.ui.main_window.messagebox.askyesno", lambda *a, **k: False)
    window._delete_map(SecretMapRef("os-keyring", "default", "keep"))
    assert len(_backend().list_secret_maps()) == 1


def test_duplicate_map(window, monkeypatch):

    quick.quick_create_password(_backend(), "orig", "x")
    window.refresh()
    monkeypatch.setattr("keynest.ui.main_window.simpledialog.askstring", lambda *a, **k: "clone")
    window._duplicate_map(SecretMapRef("os-keyring", "default", "orig"))
    paths = {r.path for r in _backend().list_secret_maps()}
    assert "/default/orig" in paths
    assert "/default/clone" in paths


def test_rename_map(window, monkeypatch):

    quick.quick_create_password(_backend(), "before", "x")
    window.refresh()
    answers = iter(["default", "after"])  # folder, then name
    monkeypatch.setattr("keynest.ui.main_window.simpledialog.askstring", lambda *a, **k: next(answers))
    window._rename_map(SecretMapRef("os-keyring", "default", "before"))
    paths = {r.path for r in _backend().list_secret_maps()}
    assert paths == {"/default/after"}


def test_diagnostics_dialog_opens(window):
    # Should construct a TextDialog without raising; just ensure it runs.
    window._show_diagnostics()


def test_backup_index_with_data(window, monkeypatch):

    quick.quick_create_password(_backend(), "m", "x")
    captured: dict[str, str] = {}
    monkeypatch.setattr("keynest.ui.main_window.messagebox.showinfo", lambda title, msg: captured.update(msg=msg))
    window._backup_index()
    assert "Backed up" in captured.get("msg", "")


# -- quick dialogs over the live window --------------------------------------


def test_quick_add_dialog_saves(window):
    from keynest.ui.quick_dialogs import QuickAddPasswordDialog

    saved: list = []
    dialog = QuickAddPasswordDialog(window, _backend(), "os-keyring", saved.append)
    dialog._name_var.set("api-key")
    dialog._value_var.set("sekret")
    dialog._save()
    assert saved == [SecretMapRef("os-keyring", "default", "api-key")]
    assert _backend().get_secret_map("default", "api-key").values == {"VALUE": "sekret"}


def test_quick_add_dialog_generate_fills_value(window):
    from keynest.ui.quick_dialogs import QuickAddPasswordDialog

    dialog = QuickAddPasswordDialog(window, _backend(), "os-keyring", lambda ref: None)
    dialog._generate()
    assert dialog._value_var.get()  # a value was generated


def test_paste_env_dialog_bulk_saves(window):
    from keynest.ui.quick_dialogs import PasteEnvDialog

    saved: list = []
    dialog = PasteEnvDialog(window, _backend(), "os-keyring", saved.append, default_path="app/dev")
    dialog._text.insert("1.0", "A=1\nB=two\n")
    dialog._save()
    assert saved == [SecretMapRef("os-keyring", "app", "dev")]
    assert _backend().get_secret_map("app", "dev").values == {"A": "1", "B": "two"}


def test_paste_env_preview_reports_count(window):
    from keynest.ui.quick_dialogs import PasteEnvDialog

    dialog = PasteEnvDialog(window, _backend(), "os-keyring", lambda ref: None)
    dialog._text.insert("1.0", "A=1\nB=2\n")
    dialog._preview()
    assert "2 key" in dialog._status.cget("text")


# -- report tool handlers (Tools menu) ---------------------------------------


def _load_current(window, **values):
    """Create + select a map so the 'current map' handlers have something."""
    quick.bulk_set_from_env(_backend(), "app/dev", "\n".join(f"{k}={v}" for k, v in values.items()))
    window.refresh()
    window._select_map(SecretMapRef("os-keyring", "app", "dev"))


def test_lint_map_clean(window, monkeypatch):
    import keynest.ui.main_window as mw

    captured: dict[str, str] = {}
    monkeypatch.setattr(mw, "TextDialog", lambda parent, title, body: captured.update(title=title, body=body))
    _load_current(window, GOOD_KEY="v")
    window._lint_map()
    assert "clean" in captured["body"]


def test_lint_map_findings(window, monkeypatch):
    import keynest.ui.main_window as mw

    captured: dict[str, str] = {}
    monkeypatch.setattr(mw, "TextDialog", lambda parent, title, body: captured.update(body=body))
    _load_current(window, **{"bad-key": "v"})
    window._lint_map()
    assert "bad-key" in captured["body"]


def test_redacted_export_hides_value(window, monkeypatch):
    import keynest.ui.main_window as mw

    captured: dict[str, str] = {}
    monkeypatch.setattr(mw, "TextDialog", lambda parent, title, body: captured.update(body=body))
    _load_current(window, PASSWORD="hunter2")
    window._redacted_export()
    assert "hunter2" not in captured["body"]
    assert "REDACTED" in captured["body"]


def test_diff_maps(window, monkeypatch):
    import keynest.ui.main_window as mw

    quick.bulk_set_from_env(_backend(), "app/prod", "A=1\nC=3")
    captured: dict[str, str] = {}
    monkeypatch.setattr(mw, "TextDialog", lambda parent, title, body: captured.update(body=body))
    monkeypatch.setattr("keynest.ui.main_window.simpledialog.askstring", lambda *a, **k: "app/prod")
    _load_current(window, A="1", B="2")
    window._diff_maps()
    assert "- B" in captured["body"] and "+ C" in captured["body"]


def test_stale_maps(window, monkeypatch):
    import keynest.ui.main_window as mw

    captured: dict[str, str] = {}
    monkeypatch.setattr(mw, "TextDialog", lambda parent, title, body: captured.update(body=body))
    monkeypatch.setattr("keynest.ui.main_window.simpledialog.askinteger", lambda *a, **k: 0)
    _load_current(window, A="1")
    window._stale_maps()
    assert "/app/dev" in captured["body"]


def test_recent_activity_empty(window, monkeypatch):
    import keynest.ui.main_window as mw

    captured: dict[str, str] = {}
    monkeypatch.setattr(mw, "TextDialog", lambda parent, title, body: captured.update(body=body))
    window._recent_activity()
    assert "no audit events" in captured["body"]


def test_keyring_help_dialog(window, monkeypatch):
    import keynest.ui.main_window as mw

    captured: dict[str, str] = {}
    monkeypatch.setattr(mw, "TextDialog", lambda parent, title, body: captured.update(body=body))
    window._show_keyring_help()
    assert "index" in captured["body"].lower()


def test_run_command_shows_keynest_run(window, monkeypatch):
    import keynest.ui.main_window as mw

    captured: dict[str, str] = {}
    monkeypatch.setattr(mw, "TextDialog", lambda parent, title, body: captured.update(body=body))
    _load_current(window, A="1")
    window._run_command()
    assert "keynest run app/dev" in captured["body"]


def test_generate_code_opens_viewer(window, monkeypatch):
    import keynest.ui.main_window as mw

    opened: dict[str, int] = {}
    monkeypatch.setattr(mw, "CodeViewerDialog", lambda parent, snippets: opened.update(n=len(snippets)))
    _load_current(window, DATABASE_URL="x")
    window._generate_code()
    assert opened["n"] > 0
