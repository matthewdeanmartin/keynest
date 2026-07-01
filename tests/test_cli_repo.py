"""CLI transparent repo relocation: bare-name resolution and overrides."""

from __future__ import annotations

import pytest

from keynest.cli import main
from keynest.services import repo_context


@pytest.fixture(autouse=True)
def _isolate(mem_keyring, devsecrets_home):
    """Run against an in-memory keyring and isolated home."""
    return None


@pytest.fixture
def in_repo(monkeypatch, tmp_path):
    """Pretend the CLI is running inside github.com/acme/acme-api."""
    ctx = repo_context.RepoContext(
        root=tmp_path,
        host="github.com",
        owner="acme",
        repo="acme-api",
        remote_url="https://github.com/acme/acme-api.git",
        source="remote",
    )
    monkeypatch.setattr("keynest.services.repo_context.detect", lambda: ctx)
    return ctx


@pytest.fixture
def no_repo(monkeypatch):
    """Pretend the CLI is not inside any repo."""
    monkeypatch.setattr("keynest.services.repo_context.detect", lambda: None)


def test_bare_name_resolves_to_repo_folder(in_repo, capsys):
    # A bare name (no slash) lands in the detected repo folder.
    assert main(["set", "dev", "A", "1"]) == 0
    capsys.readouterr()
    assert main(["list"]) == 0
    assert "/acme.acme-api/dev" in capsys.readouterr().out


def test_explicit_path_overrides_repo(in_repo, capsys):
    # An explicit folder/name always wins over the detected repo folder.
    assert main(["set", "other/dev", "A", "1"]) == 0
    capsys.readouterr()
    main(["list"])
    out = capsys.readouterr().out
    assert "/other/dev" in out
    assert "/acme.acme-api/dev" not in out


def test_no_repo_flag_disables_defaulting(in_repo, capsys):
    # --no-repo makes a bare name fall back to /default.
    assert main(["set", "dev", "A", "1", "--no-repo"]) == 0
    capsys.readouterr()
    main(["list"])
    assert "/default/dev" in capsys.readouterr().out


def test_env_var_disables_defaulting(in_repo, monkeypatch, capsys):
    monkeypatch.setenv("KEYNEST_NO_REPO", "1")
    assert main(["set", "dev", "A", "1"]) == 0
    capsys.readouterr()
    main(["list"])
    assert "/default/dev" in capsys.readouterr().out


def test_mutation_echoes_resolved_path(in_repo, capsys):
    main(["set", "dev", "A", "1"])
    err = capsys.readouterr().err
    assert "→ /acme.acme-api/dev" in err


def test_no_echo_without_repo(no_repo, capsys):
    main(["set", "dev", "A", "1"])
    err = capsys.readouterr().err
    assert "→" not in err


def test_bare_name_without_repo_is_default(no_repo, capsys):
    assert main(["set", "dev", "A", "1"]) == 0
    capsys.readouterr()
    main(["list"])
    assert "/default/dev" in capsys.readouterr().out


def test_run_resolves_bare_name(in_repo, capfd):
    import sys

    main(["set", "dev", "GREETING", "hi"])
    capfd.readouterr()
    # `run` should find the map under the repo folder via the bare name.
    # Use capfd (file-descriptor level) since run spawns a real subprocess.
    rc = main(["run", "dev", "--", sys.executable, "-c", "print('ok')"])
    assert rc == 0
    assert "ok" in capfd.readouterr().out


# -- .keynest marker via CLI (R4) -------------------------------------------- #


@pytest.fixture
def marker_repo(monkeypatch, tmp_path):
    """A repo whose identity comes from a .keynest marker with default_map."""
    ctx = repo_context.RepoContext(
        root=tmp_path,
        source="marker",
        marker_folder="team.proj",
        default_map="dev",
    )
    monkeypatch.setattr("keynest.services.repo_context.detect", lambda: ctx)
    return ctx


def test_marker_default_map_fills_empty_path(marker_repo, capsys):
    # An empty path resolves to the marker folder + default_map name.
    assert main(["set", "", "A", "1"]) == 0
    capsys.readouterr()
    main(["list"])
    assert "/team.proj/dev" in capsys.readouterr().out


def test_marker_folder_only_path_uses_default_map(marker_repo, capsys):
    # "somefolder/" (folder, no name) fills the name from default_map.
    assert main(["set", "somefolder/", "A", "1"]) == 0
    capsys.readouterr()
    main(["list"])
    assert "/somefolder/dev" in capsys.readouterr().out


def test_init_repo_writes_marker(in_repo, tmp_path, capsys):
    rc = main(["init-repo", "--folder", "my.folder", "--default-map", "dev"])
    assert rc == 0
    written = tmp_path / ".keynest"
    assert written.is_file()
    assert repo_context.read_marker(tmp_path) == ("my.folder", "dev")


def test_init_repo_infers_folder(in_repo, tmp_path):
    assert main(["init-repo"]) == 0
    assert repo_context.read_marker(tmp_path) == ("acme.acme-api", None)


def test_init_repo_refuses_overwrite_without_force(in_repo, tmp_path, capsys):
    main(["init-repo", "--folder", "one"])
    capsys.readouterr()
    rc = main(["init-repo", "--folder", "two"])
    assert rc == 2
    assert "already exists" in capsys.readouterr().err
    # Original is preserved.
    assert repo_context.read_marker(tmp_path) == ("one", None)


def test_init_repo_force_overwrites(in_repo, tmp_path):
    main(["init-repo", "--folder", "one"])
    assert main(["init-repo", "--folder", "two", "--force"]) == 0
    assert repo_context.read_marker(tmp_path) == ("two", None)


def test_init_repo_outside_repo_errors(no_repo, capsys):
    rc = main(["init-repo"])
    assert rc == 2
    assert "Not inside a git repository" in capsys.readouterr().err


def test_init_repo_dry_run_writes_nothing(in_repo, tmp_path, capsys):
    rc = main(["init-repo", "--folder", "x", "--dry-run"])
    assert rc == 0
    assert not (tmp_path / ".keynest").exists()
    assert "[dry-run]" in capsys.readouterr().out
