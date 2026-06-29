"""Tests for the OS keyring backend against an in-memory keyring."""

from __future__ import annotations

import pytest

from keynest.backends.base import SecretMapExists, SecretMapNotFound
from keynest.backends.os_keyring import OsKeyringBackend
from keynest.model import SecretMap, SecretMapRef
from keynest.services.index_store import IndexStore


@pytest.fixture
def backend(mem_keyring, devsecrets_home) -> OsKeyringBackend:
    return OsKeyringBackend(index=IndexStore())


def _map(folder="my-app", name="dev", **values) -> SecretMap:
    return SecretMap(backend="os-keyring", folder=folder, name=name, values=values or {"K": "v"})


def test_put_get_roundtrip(backend):
    backend.put_secret_map(_map(DATABASE_URL="postgres://x"))
    loaded = backend.get_secret_map("my-app", "dev")
    assert loaded.values == {"DATABASE_URL": "postgres://x"}
    assert loaded.created_at is not None


def test_get_missing_raises(backend):
    with pytest.raises(SecretMapNotFound):
        backend.get_secret_map("nope", "nope")


def test_list_secret_maps_and_folders(backend):
    backend.put_secret_map(_map(folder="a", name="one"))
    backend.put_secret_map(_map(folder="b", name="two"))
    assert backend.list_secret_maps() == [
        SecretMapRef("os-keyring", "a", "one"),
        SecretMapRef("os-keyring", "b", "two"),
    ]
    assert backend.list_secret_maps("a") == [SecretMapRef("os-keyring", "a", "one")]
    assert "a" in backend.list_folders() and "default" in backend.list_folders()


def test_delete(backend):
    backend.put_secret_map(_map())
    backend.delete_secret_map("my-app", "dev")
    assert backend.list_secret_maps() == []
    with pytest.raises(SecretMapNotFound):
        backend.delete_secret_map("my-app", "dev")


def test_create_secret_map_conflict(backend):
    backend.create_secret_map(_map())
    with pytest.raises(SecretMapExists):
        backend.create_secret_map(_map())


def test_rename(backend):
    backend.put_secret_map(_map(folder="a", name="one", SECRET="s"))
    backend.rename_secret_map(SecretMapRef("os-keyring", "a", "one"), SecretMapRef("os-keyring", "b", "two"))
    assert backend.list_secret_maps() == [SecretMapRef("os-keyring", "b", "two")]
    assert backend.get_secret_map("b", "two").values == {"SECRET": "s"}
    with pytest.raises(SecretMapNotFound):
        backend.get_secret_map("a", "one")


def test_index_persists_across_instances(backend, devsecrets_home):
    backend.put_secret_map(_map())
    fresh = OsKeyringBackend(index=IndexStore())
    assert fresh.list_secret_maps() == [SecretMapRef("os-keyring", "my-app", "dev")]


def test_test_connection_ok(backend):
    status = backend.test_connection()
    assert status.ok
