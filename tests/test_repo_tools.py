"""Tests for repo hygiene helpers."""

from __future__ import annotations

from keynest.services import repo_tools


def test_scan_finds_env_and_secret_files(tmp_path):
    (tmp_path / ".env").write_text("A=1")
    (tmp_path / ".env.local").write_text("B=2")
    (tmp_path / "server.pem").write_text("x")
    (tmp_path / "id.key").write_text("x")
    (tmp_path / "credentials").write_text("x")
    (tmp_path / "readme.txt").write_text("not a secret")
    sub = tmp_path / "nested"
    sub.mkdir()
    (sub / "prod.env").write_text("C=3")

    found = repo_tools.scan_for_env_files(str(tmp_path))
    names = {p.rsplit("\\", 1)[-1].rsplit("/", 1)[-1] for p in found}
    assert names == {".env", ".env.local", "server.pem", "id.key", "credentials", "prod.env"}
    assert "readme.txt" not in names


def test_scan_skips_vendor_dirs(tmp_path):
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / ".env").write_text("should be ignored")
    (tmp_path / ".env").write_text("kept")

    found = repo_tools.scan_for_env_files(str(tmp_path))
    assert len(found) == 1
    assert "node_modules" not in found[0]


def test_scan_respects_max_results(tmp_path):
    for i in range(5):
        (tmp_path / f".env.{i}").write_text("x")
    assert len(repo_tools.scan_for_env_files(str(tmp_path), max_results=2)) == 2


def test_scan_missing_dir_returns_empty(tmp_path):
    assert repo_tools.scan_for_env_files(str(tmp_path / "nope")) == []


def test_gitignore_suggestions_all_when_empty():
    assert repo_tools.gitignore_suggestions("") == repo_tools.GITIGNORE_SUGGESTIONS


def test_gitignore_suggestions_filters_present():
    existing = ".env\n*.pem\n"
    suggestions = repo_tools.gitignore_suggestions(existing)
    assert ".env" not in suggestions
    assert "*.pem" not in suggestions
    assert ".env.*" in suggestions
