"""Tests for :mod:`keynest.backends.keyring_enumerate`.

The platform-specific enumerators talk to real OS credential stores, so these
tests exercise the platform-agnostic machinery (dispatch, chainer unwrapping,
fallback) and the Windows compound-name decode against injected fakes rather
than a live keyring.
"""

from __future__ import annotations

import sys
import types
import typing

import pytest

from keynest.backends import keyring_enumerate as ke

if typing.TYPE_CHECKING:
    from keyring.backend import KeyringBackend


class _FakeBackend:
    """Stand-in for a keyring backend with a controllable module/class name."""


def _named_backend(module: str, qualname: str):
    """Return a backend instance whose type reports ``module.qualname``."""
    cls = type(qualname, (_FakeBackend,), {})
    cls.__module__ = module
    return cls()


# --------------------------------------------------------------------------- #
# _unwrap: chainer expansion
# --------------------------------------------------------------------------- #
def test_unwrap_plain_backend_yields_itself():
    backend = _named_backend("some.module", "Plain")
    assert list(ke._unwrap(backend)) == [backend]


def test_unwrap_expands_chainer_members_in_order():
    a = _named_backend("m", "A")
    b = _named_backend("m", "B")
    chainer = types.SimpleNamespace(backends=[a, b])
    assert list(ke._unwrap(chainer)) == [a, b]


def test_unwrap_recurses_into_nested_chainers():
    a = _named_backend("m", "A")
    inner = types.SimpleNamespace(backends=[a])
    outer = types.SimpleNamespace(backends=[inner])
    assert list(ke._unwrap(outer)) == [a]


# --------------------------------------------------------------------------- #
# _dispatch
# --------------------------------------------------------------------------- #
def test_dispatch_matches_registered_backend():
    backend = _named_backend("keyring.backends.Windows", "WinVaultKeyring")
    assert ke._dispatch(backend) is ke._enumerate_windows


def test_dispatch_returns_none_for_unknown():
    backend = _named_backend("third.party", "Mystery")
    assert ke._dispatch(backend) is None


# --------------------------------------------------------------------------- #
# list_credentials: dispatch, fallthrough, error
# --------------------------------------------------------------------------- #
def test_list_credentials_uses_first_enumerable_in_chain(monkeypatch):
    target = _named_backend("keyring.backends.Windows", "WinVaultKeyring")
    unknown = _named_backend("third.party", "Mystery")
    chainer = types.SimpleNamespace(backends=[unknown, target])

    sentinel = [ke.Credential("svc", "user")]
    monkeypatch.setitem(ke._ENUMERATORS, ke._qualname(target), lambda b: iter(sentinel))

    # chainer is a structural stand-in for a ChainerBackend (which is not a
    # KeyringBackend subclass); list_credentials only reads ``.backends``.
    assert list(ke.list_credentials(typing.cast("KeyringBackend", chainer))) == sentinel


def test_list_credentials_raises_when_nothing_enumerable():
    backend = _named_backend("third.party", "Mystery")
    with pytest.raises(ke.EnumerationNotSupported):
        list(ke.list_credentials(backend))


def test_list_credentials_defaults_to_active_keyring(monkeypatch):
    backend = _named_backend("keyring.backends.Windows", "WinVaultKeyring")
    monkeypatch.setattr("keyring.get_keyring", lambda: backend)
    monkeypatch.setitem(
        ke._ENUMERATORS,
        ke._qualname(backend),
        lambda b: iter([ke.Credential("s", "u")]),
    )
    assert list(ke.list_credentials()) == [ke.Credential("s", "u")]


# --------------------------------------------------------------------------- #
# Windows enumerator: compound-name decode, missing username
# --------------------------------------------------------------------------- #
class _FakeWin32Cred(types.ModuleType):
    """A fake ``win32cred`` module whose ``CredEnumerate`` returns canned data."""

    creds: typing.ClassVar[list[dict]] = []
    enumerate_returns_none: bool = False

    def CredEnumerate(self, flt, flags):
        return None if self.enumerate_returns_none else list(self.creds)


@pytest.fixture
def fake_win32cred(monkeypatch):
    """Install a fake ``win32cred`` module returning canned credentials."""
    module = _FakeWin32Cred("win32cred")
    monkeypatch.setitem(sys.modules, "win32cred", module)
    # Ensure the pywin32-ctypes import path fails so the fallback import wins.
    monkeypatch.setitem(sys.modules, "win32ctypes.pywin32", None)
    return module


def test_windows_plain_credential(fake_win32cred):
    fake_win32cred.creds = [{"TargetName": "github", "UserName": "alice"}]
    assert list(ke._enumerate_windows(_FakeBackend())) == [ke.Credential("github", "alice")]


def test_windows_compound_name_is_decoded(fake_win32cred):
    # keyring stores collisions under "{user}@{service}".
    fake_win32cred.creds = [{"TargetName": "bob@github", "UserName": "bob"}]
    assert list(ke._enumerate_windows(_FakeBackend())) == [ke.Credential("github", "bob")]


def test_windows_missing_username_becomes_none(fake_win32cred):
    fake_win32cred.creds = [{"TargetName": "svc", "UserName": ""}]
    assert list(ke._enumerate_windows(_FakeBackend())) == [ke.Credential("svc", None)]


def test_windows_empty_enumeration(fake_win32cred):
    fake_win32cred.enumerate_returns_none = True
    assert not list(ke._enumerate_windows(_FakeBackend()))
