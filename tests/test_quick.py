"""Tests for the low-friction quick-create / bulk-paste helpers."""

from __future__ import annotations

import pytest

from keynest.backends.os_keyring import OsKeyringBackend
from keynest.services import quick
from keynest.services.index_store import IndexStore


@pytest.fixture
def backend(mem_keyring, devsecrets_home) -> OsKeyringBackend:
    return OsKeyringBackend(index=IndexStore())


def test_quick_create_password_single_key(backend):
    sm = quick.quick_create_password(backend, "github-token", "xyzzy")
    assert sm.path == "/default/github-token"
    assert sm.values == {"VALUE": "xyzzy"}
    # Round-trips through the backend.
    assert backend.get_secret_map("default", "github-token").values == {"VALUE": "xyzzy"}


def test_quick_create_password_strips_name(backend):
    sm = quick.quick_create_password(backend, "  spaced  ", "v")
    assert sm.name == "spaced"


def test_quick_create_password_rejects_blank(backend):
    with pytest.raises(ValueError):
        quick.quick_create_password(backend, "   ", "v")


def test_quick_create_password_custom_folder_and_key(backend):
    sm = quick.quick_create_password(backend, "db", "pw", folder="client-x", key="DATABASE_PASSWORD")
    assert sm.path == "/client-x/db"
    assert sm.values == {"DATABASE_PASSWORD": "pw"}


def test_preview_env_reports_warnings():
    result = quick.preview_env("A=1\nbad-key=2")
    assert result.values == {"A": "1", "bad-key": "2"}
    assert any("bad-key" in w for w in result.warnings)


def test_bulk_set_creates_map(backend):
    sm, result = quick.bulk_set_from_env(backend, "app/dev", "A=1\nB=two\n")
    assert sm.path == "/app/dev"
    assert sm.values == {"A": "1", "B": "two"}
    assert not result.warnings


def test_bulk_set_merges_into_existing(backend):
    quick.quick_create_password(backend, "dev", "old", folder="app", key="EXISTING")
    sm, _ = quick.bulk_set_from_env(backend, "app/dev", "NEW=1\n")
    assert sm.values == {"EXISTING": "old", "NEW": "1"}


def test_bulk_set_rejects_empty(backend):
    with pytest.raises(ValueError):
        quick.bulk_set_from_env(backend, "app/dev", "# just a comment\n\n")
