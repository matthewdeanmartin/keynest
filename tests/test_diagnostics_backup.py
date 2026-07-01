"""Tests for diagnostics collection and index backup."""

from __future__ import annotations

from keynest.model import SecretMap
from keynest.services import diagnostics
from keynest.services.index_store import IndexStore


def test_diagnostics_collects_keyring_and_paths(mem_keyring, devsecrets_home):
    diag = diagnostics.collect(index=IndexStore())
    assert diag.python_version
    assert diag.keyring_backend == "MemoryKeyring"
    assert "index" in "\n".join(diag.as_lines())


def test_diagnostics_reports_index_item_count(mem_keyring, devsecrets_home):
    index = IndexStore()
    index.upsert(SecretMap(backend="os-keyring", folder="f", name="m", values={"A": "1"}))
    index.save()
    diag = diagnostics.collect(index=IndexStore())
    assert diag.index_exists
    assert diag.index_item_count == 1


def test_diagnostics_reports_detected_repo(mem_keyring, devsecrets_home, monkeypatch, tmp_path):
    from keynest.services import repo_context

    ctx = repo_context.RepoContext(
        root=tmp_path,
        host="github.com",
        owner="acme",
        repo="acme-api",
        remote_url="https://github.com/acme/acme-api.git",
        source="remote",
    )
    monkeypatch.setattr("keynest.services.repo_context.detect", lambda: ctx)
    diag = diagnostics.collect(index=IndexStore())
    assert diag.repo_detected
    assert diag.repo_default_folder == "acme.acme-api"
    joined = "\n".join(diag.as_lines())
    assert "acme/acme-api" in joined
    assert "/acme.acme-api" in joined


def test_diagnostics_reports_no_repo(mem_keyring, devsecrets_home, monkeypatch):
    monkeypatch.setattr("keynest.services.repo_context.detect", lambda: None)
    diag = diagnostics.collect(index=IndexStore())
    assert not diag.repo_detected
    assert "repo: none detected" in "\n".join(diag.as_lines())


def test_backup_returns_none_without_index(devsecrets_home):
    assert IndexStore().backup() is None


def test_backup_copies_index(devsecrets_home):
    index = IndexStore()
    index.upsert(SecretMap(backend="os-keyring", folder="f", name="m", values={"A": "1"}))
    index.save()
    backup = index.backup()
    assert backup is not None
    assert backup.exists()
    assert backup.read_bytes() == index.path.read_bytes()
