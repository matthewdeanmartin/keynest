"""Tests for repo detection and folder defaulting (transparent relocation)."""

from __future__ import annotations

from pathlib import Path

import pytest

from keynest.services import repo_context as rc

# -- parse_remote_url --------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("git@github.com:acme/acme-api.git", ("github.com", "acme", "acme-api")),
        ("https://github.com/acme/acme-api.git", ("github.com", "acme", "acme-api")),
        ("https://github.com/acme/acme-api", ("github.com", "acme", "acme-api")),
        ("git@gitlab.com:acme/group/api.git", ("gitlab.com", "acme/group", "api")),
        ("https://gitlab.com/acme/group/sub/api", ("gitlab.com", "acme/group/sub", "api")),
        ("https://ghe.corp.example/acme/x.git", ("ghe.corp.example", "acme", "x")),
        ("ssh://git@github.com:22/acme/api.git", ("github.com", "acme", "api")),
        # Host case is normalized to lowercase.
        ("git@GitHub.com:Acme/Api.git", ("github.com", "Acme", "Api")),
    ],
)
def test_parse_remote_url(url, expected):
    assert rc.parse_remote_url(url) == expected


def test_parse_remote_url_scrubs_credentials():
    host, owner, repo = rc.parse_remote_url("https://user:token@github.com/acme/api.git")
    assert (host, owner, repo) == ("github.com", "acme", "api")


@pytest.mark.parametrize("url", ["not-a-url", "", "file:///local/path", "github.com"])
def test_parse_remote_url_unparseable(url):
    assert rc.parse_remote_url(url) == (None, None, None)


def test_scrub_credentials_removes_userinfo():
    scrubbed = rc._scrub_credentials("https://user:tok@github.com/a/b.git")
    assert "user" not in scrubbed and "tok" not in scrubbed
    assert scrubbed == "https://github.com/a/b.git"


# -- folder derivation -------------------------------------------------------


def test_folder_for_repo_owner_and_repo():
    assert rc.folder_for_repo("acme", "acme-api", None) == "acme.acme-api"


def test_folder_for_repo_gitlab_subgroup_flattened():
    assert rc.folder_for_repo("acme/group", "api", None) == "acme.group.api"


def test_folder_for_repo_repo_only():
    assert rc.folder_for_repo(None, "api", None) == "api"


def test_folder_for_repo_falls_back_to_dir_name(tmp_path):
    d = tmp_path / "my-project"
    d.mkdir()
    assert rc.folder_for_repo(None, None, d) == "my-project"


def test_folder_for_repo_sanitizes_weird_chars():
    assert rc.folder_for_repo("a b", "we!rd/name", None) == "a-b.we-rd.name"


# -- detection (fixture repos) ----------------------------------------------


def _make_repo(root: Path, remote: str | None = None, git_file: str | None = None) -> None:
    """Create a fake repo at ``root`` with an optional origin remote."""
    git_dir = root / ".git"
    if git_file is not None:
        # Worktree/submodule style: .git is a file pointing elsewhere.
        real = root.parent / "real-gitdir"
        real.mkdir(parents=True, exist_ok=True)
        (root).mkdir(parents=True, exist_ok=True)
        (root / ".git").write_text(f"gitdir: {real}\n", encoding="utf-8")
        git_dir = real
    else:
        git_dir.mkdir(parents=True, exist_ok=True)
    if remote is not None:
        (git_dir / "config").write_text(f'[remote "origin"]\n\turl = {remote}\n', encoding="utf-8")


def test_detect_none_outside_repo(tmp_path):
    assert rc.detect(tmp_path) is None


def test_detect_remote_repo(tmp_path):
    repo = tmp_path / "acme-api"
    repo.mkdir()
    _make_repo(repo, remote="git@github.com:acme/acme-api.git")
    ctx = rc.detect(repo)
    assert ctx is not None
    assert ctx.source == "remote"
    assert ctx.host == "github.com"
    assert ctx.owner == "acme"
    assert ctx.repo == "acme-api"
    assert ctx.default_folder == "acme.acme-api"
    assert ctx.slug == "acme/acme-api"


def test_detect_walks_up_to_root(tmp_path):
    repo = tmp_path / "acme-api"
    (repo / "src" / "deep").mkdir(parents=True)
    _make_repo(repo, remote="https://github.com/acme/acme-api.git")
    ctx = rc.detect(repo / "src" / "deep")
    assert ctx is not None and ctx.repo == "acme-api"


def test_detect_no_remote_uses_dir_name(tmp_path):
    repo = tmp_path / "local-only"
    repo.mkdir()
    _make_repo(repo, remote=None)
    ctx = rc.detect(repo)
    assert ctx is not None
    assert ctx.source == "local-dir"
    assert ctx.default_folder == "local-only"


def test_detect_git_file_worktree(tmp_path):
    repo = tmp_path / "wt"
    _make_repo(repo, remote="git@github.com:acme/wt.git", git_file="yes")
    ctx = rc.detect(repo)
    assert ctx is not None
    assert ctx.repo == "wt" and ctx.owner == "acme"


def test_detect_malformed_config_is_failsafe(tmp_path):
    repo = tmp_path / "broken"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / ".git" / "config").write_text("this is not ini [[[", encoding="utf-8")
    ctx = rc.detect(repo)
    # Degrades to local-dir identity instead of raising.
    assert ctx is not None
    assert ctx.source == "local-dir"
    assert ctx.default_folder == "broken"


def test_detect_remote_url_is_scrubbed(tmp_path):
    repo = tmp_path / "sec"
    repo.mkdir()
    _make_repo(repo, remote="https://user:secret-token@github.com/acme/sec.git")
    ctx = rc.detect(repo)
    assert ctx is not None
    assert ctx.remote_url is not None
    assert "secret-token" not in ctx.remote_url
    assert "user" not in ctx.remote_url


def test_detect_prefers_origin_over_other_remotes(tmp_path):
    repo = tmp_path / "multi"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / ".git" / "config").write_text(
        '[remote "upstream"]\n\turl = git@github.com:up/multi.git\n'
        '[remote "origin"]\n\turl = git@github.com:me/multi.git\n',
        encoding="utf-8",
    )
    ctx = rc.detect(repo)
    assert ctx is not None and ctx.owner == "me"


# -- .keynest marker (R4) ---------------------------------------------------- #


def test_validate_marker_folder_only():
    assert rc.validate_marker({"folder": "acme.api"}) == ("acme.api", None)


def test_validate_marker_with_default_map():
    assert rc.validate_marker({"folder": "acme.api", "default_map": "dev"}) == ("acme.api", "dev")


def test_validate_marker_rejects_unknown_keys():
    # An unknown key (e.g. a smuggled secret) is refused.
    with pytest.raises(rc.MarkerError):
        rc.validate_marker({"folder": "x", "password": "hunter2"})


def test_validate_marker_requires_folder():
    with pytest.raises(rc.MarkerError):
        rc.validate_marker({"default_map": "dev"})


def test_validate_marker_rejects_non_string_folder():
    with pytest.raises(rc.MarkerError):
        rc.validate_marker({"folder": 123})


def test_read_marker_absent_returns_none(tmp_path):
    assert rc.read_marker(tmp_path) is None


def test_read_marker_roundtrip(tmp_path):
    (tmp_path / ".keynest").write_text('folder = "team.proj"\ndefault_map = "dev"\n', encoding="utf-8")
    assert rc.read_marker(tmp_path) == ("team.proj", "dev")


def test_read_marker_malformed_raises(tmp_path):
    (tmp_path / ".keynest").write_text("this is = = not toml", encoding="utf-8")
    with pytest.raises(rc.MarkerError):
        rc.read_marker(tmp_path)


def test_write_marker_creates_valid_file(tmp_path):
    path = rc.write_marker(tmp_path, "acme.api", default_map="dev")
    assert path == tmp_path / ".keynest"
    # It round-trips through the reader.
    assert rc.read_marker(tmp_path) == ("acme.api", "dev")
    # And it is documented as secret-free.
    text = path.read_text(encoding="utf-8")
    assert "NO secret" in text


def test_write_marker_refuses_invalid_folder(tmp_path):
    with pytest.raises(rc.MarkerError):
        rc.write_marker(tmp_path, "")


def test_write_marker_escapes_quotes(tmp_path):
    rc.write_marker(tmp_path, 'we"ird')
    assert rc.read_marker(tmp_path) == ('we"ird', None)


def test_detect_marker_overrides_remote(tmp_path):
    # A repo whose remote says acme/api, but a marker points elsewhere.
    repo = tmp_path / "acme-api"
    repo.mkdir()
    _make_repo(repo, remote="git@github.com:acme/acme-api.git")
    (repo / ".keynest").write_text('folder = "custom-folder"\ndefault_map = "stg"\n', encoding="utf-8")
    ctx = rc.detect(repo)
    assert ctx is not None
    assert ctx.source == "marker"
    assert ctx.default_folder == "custom-folder"
    assert ctx.default_map == "stg"
    assert ctx.slug == "custom-folder"


def test_detect_malformed_marker_falls_through_to_remote(tmp_path):
    repo = tmp_path / "acme-api"
    repo.mkdir()
    _make_repo(repo, remote="git@github.com:acme/acme-api.git")
    (repo / ".keynest").write_text("garbage = = =", encoding="utf-8")
    ctx = rc.detect(repo)
    # Malformed marker is ignored; inference still works.
    assert ctx is not None
    assert ctx.source == "remote"
    assert ctx.default_folder == "acme.acme-api"
