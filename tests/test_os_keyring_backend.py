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


# -- keyring-authoritative listing ------------------------------------------- #


def test_listing_recovers_map_present_in_keyring_but_missing_from_index(backend, mem_keyring):
    """A map written straight to the keyring shows up even with no index entry."""
    import json

    from keynest.model import SERVICE_NAME_HINT

    mem_keyring.set_password(SERVICE_NAME_HINT, "/strays/found", json.dumps({"K": "v"}))
    assert SecretMapRef("os-keyring", "strays", "found") in backend.list_secret_maps()


def test_listing_omits_map_in_index_but_absent_from_keyring(backend, mem_keyring):
    """If the keyring no longer holds a map, the index alone can't resurrect it."""
    backend.put_secret_map(_map(folder="a", name="one"))
    # Simulate drift: the credential vanishes from the keyring out-of-band.
    from keynest.model import SERVICE_NAME_HINT

    mem_keyring.delete_password(SERVICE_NAME_HINT, "/a/one")
    assert backend.list_secret_maps() == []


def test_listing_ignores_other_services(backend, mem_keyring):
    """Credentials under unrelated service names are not treated as our maps."""
    mem_keyring.set_password("SomeOtherApp", "/a/one", "x")
    backend.put_secret_map(_map(folder="a", name="mine"))
    assert backend.list_secret_maps() == [SecretMapRef("os-keyring", "a", "mine")]


def test_listing_falls_back_to_index_when_not_enumerable(backend, mem_keyring, monkeypatch):
    """When enumeration is unsupported, listing is served from the index."""
    from keynest.backends import keyring_enumerate

    def _raise(_backend):
        raise keyring_enumerate.EnumerationNotSupported("nope")

    monkeypatch.setattr(keyring_enumerate, "list_credentials", _raise)
    backend.put_secret_map(_map(folder="a", name="one"))
    assert backend.list_secret_maps() == [SecretMapRef("os-keyring", "a", "one")]


# -- raw (non-keynest) credential listing ------------------------------------ #


def test_list_raw_credentials_excludes_keynest_maps(backend, mem_keyring):
    """Raw listing surfaces other apps' creds but not keynest's own maps."""
    from keynest.model import RawCredential

    backend.put_secret_map(_map(folder="a", name="mine"))  # under our service
    mem_keyring.set_password("git:https://github.com", "alice", "tok")
    # A credential with no username (write to the store directly to avoid
    # keyring's empty-username deprecation warning).
    mem_keyring._store[("AWS", "")] = "secret"

    raw = backend.list_raw_credentials()

    assert RawCredential("git:https://github.com", "alice") in raw
    assert RawCredential("AWS", None) in raw
    # keynest's own service name must never appear in the raw list.
    assert all("DeveloperSecretWorkbench" not in c.service for c in raw)


def test_list_raw_credentials_sorted(backend, mem_keyring):
    from keynest.model import RawCredential

    mem_keyring.set_password("zeta", "u", "v")
    mem_keyring.set_password("alpha", "u", "v")
    raw = backend.list_raw_credentials()
    assert raw == [RawCredential("alpha", "u"), RawCredential("zeta", "u")]


def test_list_raw_credentials_empty_when_not_enumerable(backend, mem_keyring, monkeypatch):
    from keynest.backends import keyring_enumerate

    def _raise(_backend):
        raise keyring_enumerate.EnumerationNotSupported("nope")

    monkeypatch.setattr(keyring_enumerate, "list_credentials", _raise)
    mem_keyring.set_password("git", "u", "v")
    assert backend.list_raw_credentials() == []
