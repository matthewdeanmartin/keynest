"""Light integration tests for the Tk panels and dialogs.

These build real widgets on a hidden root and drive them through their public
APIs (and the internal handlers the buttons bind to), asserting on observable
widget state. Modal dialog calls are stubbed where unavoidable.
"""

from __future__ import annotations

from keynest.model import SecretMap, SecretMapRef
from keynest.services import codegen
from keynest.ui.actions_panel import ActionsPanel
from keynest.ui.dialogs import CodeViewerDialog, TextDialog
from keynest.ui.folder_panel import FolderPanel
from keynest.ui.secret_editor import MASK, SecretEditor

# -- ActionsPanel ------------------------------------------------------------


def test_actions_panel_renders_buttons_and_invokes(tk_root):
    calls = []
    actions = {
        "Run": lambda: calls.append("run"),
        "---": lambda: None,  # separator, not a button
        "Copy": lambda: calls.append("copy"),
    }
    panel = ActionsPanel(tk_root, actions)
    buttons = [w for w in panel.winfo_children() if w.winfo_class() == "TButton"]
    assert len(buttons) == 2
    buttons[0].invoke()
    buttons[1].invoke()
    assert calls == ["run", "copy"]


# -- FolderPanel -------------------------------------------------------------


def _folder_panel(tk_root, selected):
    return FolderPanel(
        tk_root,
        on_select_map=lambda ref: selected.append(("select", ref)),
        on_new_map=lambda folder: selected.append(("new", folder)),
        on_backend_change=lambda b: selected.append(("backend", b)),
        on_delete_map=lambda ref: selected.append(("delete", ref)),
        on_rename_map=lambda ref: selected.append(("rename", ref)),
        on_duplicate_map=lambda ref: selected.append(("duplicate", ref)),
    )


def test_folder_panel_lists_folders_and_maps(tk_root):
    events = []
    panel = _folder_panel(tk_root, events)
    refs = [
        SecretMapRef("os-keyring", "app", "dev"),
        SecretMapRef("os-keyring", "app", "prod"),
        SecretMapRef("os-keyring", "other", "x"),
    ]
    panel.set_data(["app", "default", "other"], refs)
    # The first folder is auto-selected; its maps populate the map list.
    assert panel.selected_folder() == "app"
    names = list(panel._maps.get(0, "end"))
    assert names == ["dev", "prod"]


def test_folder_panel_selected_ref_and_delete_callback(tk_root):
    events = []
    panel = _folder_panel(tk_root, events)
    panel.set_data(["app"], [SecretMapRef("os-keyring", "app", "dev")])
    panel._maps.selection_set(0)
    assert panel.selected_ref() == SecretMapRef("os-keyring", "app", "dev")
    panel._delete_map()
    assert ("delete", SecretMapRef("os-keyring", "app", "dev")) in events


def test_folder_panel_backend_filter(tk_root):
    events = []
    panel = _folder_panel(tk_root, events)
    panel._backend_var.set("AWS Secrets Manager")
    panel._backend_changed()
    assert ("backend", "aws-secrets-manager") in events
    assert panel.active_backend_id() == "aws-secrets-manager"


def test_folder_panel_all_backends_is_none(tk_root):
    panel = _folder_panel(tk_root, [])
    panel._backend_var.set("All")
    assert panel.active_backend_id() is None


# -- SecretEditor ------------------------------------------------------------


def _editor(tk_root, saved=None, copied=None):
    saved = saved if saved is not None else []
    copied = copied if copied is not None else []
    return SecretEditor(
        tk_root,
        on_save=saved.append,
        on_copy_value=lambda k, v: copied.append((k, v)),
    )


def test_editor_masks_values_by_default(tk_root):
    editor = _editor(tk_root)
    editor.load(SecretMap(backend="os-keyring", folder="f", name="m", values={"A": "secret"}))
    row = editor._tree.item("A", "values")
    assert row[0] == "A"
    assert row[1] == MASK  # value masked


def test_editor_reveal_shows_value(tk_root):
    editor = _editor(tk_root)
    editor.load(SecretMap(backend="os-keyring", folder="f", name="m", values={"A": "secret"}))
    editor._tree.selection_set("A")
    editor._toggle_reveal()
    assert editor._tree.item("A", "values")[1] == "secret"
    # Rebuilding the rows clears the selection, so re-select to hide again.
    editor._tree.selection_set("A")
    editor._toggle_reveal()
    assert editor._tree.item("A", "values")[1] == MASK


def test_editor_kind_column_config_vs_secret(tk_root):
    editor = _editor(tk_root)
    editor.load(
        SecretMap(
            backend="os-keyring",
            folder="f",
            name="m",
            values={"PASSWORD": "p", "HOST": "h"},
            non_secret_keys=["HOST"],
        )
    )
    assert editor._tree.item("HOST", "values")[2] == "config"
    assert editor._tree.item("PASSWORD", "values")[2] == "secret"


def test_editor_copy_value_invokes_callback(tk_root):
    copied = []
    editor = _editor(tk_root, copied=copied)
    editor.load(SecretMap(backend="os-keyring", folder="f", name="m", values={"A": "v"}))
    editor._tree.selection_set("A")
    editor._copy_value()
    assert copied == [("A", "v")]


def test_editor_save_collects_description_and_tags(tk_root):
    saved = []
    editor = _editor(tk_root, saved=saved)
    editor.load(SecretMap(backend="os-keyring", folder="f", name="m", values={"A": "v"}))
    editor._desc_var.set("  my desc  ")
    editor._tags_var.set("one, two ,three")
    editor._save()
    assert len(saved) == 1
    assert saved[0].description == "my desc"
    assert saved[0].tags == ["one", "two", "three"]


def test_editor_generate_fills_and_reveals(tk_root):
    editor = _editor(tk_root)
    sm = SecretMap(backend="os-keyring", folder="f", name="m", values={"TOKEN": ""})
    editor.load(sm)
    editor._tree.selection_set("TOKEN")
    editor._generate_value()
    assert sm.values["TOKEN"]  # non-empty generated value
    assert editor._tree.item("TOKEN", "values")[1] == sm.values["TOKEN"]  # revealed


def test_editor_clear_resets_title(tk_root):
    editor = _editor(tk_root)
    editor.load(SecretMap(backend="os-keyring", folder="f", name="m", values={"A": "v"}))
    editor.load(None)
    assert "no secret map" in editor._title.cget("text").lower()
    assert not editor._tree.get_children()


def test_editor_add_key(tk_root, monkeypatch):
    editor = _editor(tk_root)
    sm = SecretMap(backend="os-keyring", folder="f", name="m", values={})
    editor.load(sm)
    answers = iter(["NEW_KEY", "the-value"])
    monkeypatch.setattr("keynest.ui.secret_editor.simpledialog.askstring", lambda *a, **k: next(answers))
    editor._add_key()
    assert sm.values == {"NEW_KEY": "the-value"}


def test_editor_add_bad_key_confirmed(tk_root, monkeypatch):
    editor = _editor(tk_root)
    sm = SecretMap(backend="os-keyring", folder="f", name="m", values={})
    editor.load(sm)
    answers = iter(["bad-key", "v"])
    monkeypatch.setattr("keynest.ui.secret_editor.simpledialog.askstring", lambda *a, **k: next(answers))
    monkeypatch.setattr("keynest.ui.secret_editor.messagebox.askyesno", lambda *a, **k: True)  # add anyway
    editor._add_key()
    assert sm.values == {"bad-key": "v"}


def test_editor_edit_value(tk_root, monkeypatch):
    editor = _editor(tk_root)
    sm = SecretMap(backend="os-keyring", folder="f", name="m", values={"A": "old"})
    editor.load(sm)
    editor._tree.selection_set("A")
    monkeypatch.setattr("keynest.ui.secret_editor.simpledialog.askstring", lambda *a, **k: "new")
    editor._edit_value()
    assert sm.values["A"] == "new"


def test_editor_rename_key(tk_root, monkeypatch):
    editor = _editor(tk_root)
    sm = SecretMap(backend="os-keyring", folder="f", name="m", values={"A": "v"})
    editor.load(sm)
    editor._tree.selection_set("A")
    monkeypatch.setattr("keynest.ui.secret_editor.simpledialog.askstring", lambda *a, **k: "B")
    editor._rename_key()
    assert sm.values == {"B": "v"}


def test_editor_delete_key(tk_root, monkeypatch):
    editor = _editor(tk_root)
    sm = SecretMap(backend="os-keyring", folder="f", name="m", values={"A": "v", "B": "w"})
    editor.load(sm)
    editor._tree.selection_set("A")
    monkeypatch.setattr("keynest.ui.secret_editor.messagebox.askyesno", lambda *a, **k: True)
    editor._delete_key()
    assert sm.values == {"B": "w"}


# -- dialogs -----------------------------------------------------------------


def test_text_dialog_shows_content(tk_root):
    import tkinter as tk
    from typing import cast

    dialog = TextDialog(tk_root, "Title", "hello world")
    text_widgets = [w for w in dialog.winfo_children() if w.winfo_class() == "Text"]
    assert text_widgets
    assert "hello world" in cast(tk.Text, text_widgets[0]).get("1.0", "end")
    dialog.destroy()


def test_code_viewer_shows_first_snippet(tk_root):
    sm = SecretMap(backend="os-keyring", folder="app", name="dev", values={"DATABASE_URL": "x"})
    snippets = codegen.all_snippets(sm)
    dialog = CodeViewerDialog(tk_root, snippets)
    shown = dialog._text.get("1.0", "end")
    assert snippets[0].code.strip() in shown
    dialog.destroy()
