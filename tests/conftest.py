"""Shared pytest fixtures: an in-memory keyring and isolated DEVSECRETS_HOME."""

from __future__ import annotations

from collections.abc import Iterator

import keyring
import pytest
from keyring.backend import KeyringBackend


class MemoryKeyring(KeyringBackend):
    """A keyring backend that stores credentials in a process-local dict."""

    priority = 1

    def __init__(self) -> None:
        """Start with an empty store."""
        super().__init__()
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        """Return the stored password or ``None``."""
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        """Store a password."""
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        """Delete a password, raising if absent (matches keyring semantics)."""
        if (service, username) not in self._store:
            from keyring.errors import PasswordDeleteError

            raise PasswordDeleteError("not found")
        del self._store[(service, username)]


@pytest.fixture
def mem_keyring() -> Iterator[MemoryKeyring]:
    """Install a fresh in-memory keyring for the duration of a test."""
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    try:
        yield backend
    finally:
        keyring.set_keyring(previous)


@pytest.fixture
def devsecrets_home(tmp_path, monkeypatch) -> str:
    """Point ``DEVSECRETS_HOME`` at an isolated temporary directory."""
    home = tmp_path / "devsecrets"
    monkeypatch.setenv("DEVSECRETS_HOME", str(home))
    return str(home)


@pytest.fixture
def tk_root() -> Iterator[object]:
    """Provide a hidden Tk root window, skipping the test if no display exists.

    The widget tests are light integration tests: they build real Tk widgets on
    this root and drive them through their public APIs. Pending ``after`` jobs
    are flushed and the root destroyed on teardown.
    """
    import tkinter as tk

    try:
        root = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - headless CI without a display
        pytest.skip(f"no Tk display available: {exc}")
    root.withdraw()
    try:
        yield root
    finally:
        try:
            root.update_idletasks()
            root.destroy()
        except tk.TclError:  # pragma: no cover - already torn down
            pass
