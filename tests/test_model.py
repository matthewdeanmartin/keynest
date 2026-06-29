"""Tests for the core model: paths, validation, and warnings."""

from __future__ import annotations

import pytest

from keynest.model import (
    SecretMap,
    SecretMapRef,
    is_valid_bash_name,
    key_warning,
    logical_path,
    normalize_folder,
    parse_path,
    value_warnings,
)


@pytest.mark.parametrize(
    "raw,expected",
    [(None, "default"), ("", "default"), ("/", "default"), ("/my-app/", "my-app"), ("x", "x")],
)
def test_normalize_folder(raw, expected):
    assert normalize_folder(raw) == expected


def test_logical_path():
    assert logical_path("my-app", "dev") == "/my-app/dev"


@pytest.mark.parametrize(
    "path,folder,name",
    [
        ("my-app/dev", "my-app", "dev"),
        ("/my-app/dev", "my-app", "dev"),
        ("github", "default", "github"),
    ],
)
def test_parse_path(path, folder, name):
    assert parse_path(path) == (folder, name)


def test_parse_path_requires_name():
    with pytest.raises(ValueError):
        parse_path("my-app/")


@pytest.mark.parametrize("good", ["DATABASE_URL", "_X", "API_TOKEN_2"])
def test_valid_bash_names(good):
    assert is_valid_bash_name(good)
    assert key_warning(good) is None


@pytest.mark.parametrize("bad", ["database-url", "1TOKEN", ""])
def test_bad_bash_names_warn(bad):
    assert not is_valid_bash_name(bad)
    assert key_warning(bad) is not None


def test_value_warnings_detect_whitespace_and_newline():
    assert value_warnings(" x") == ["Value has leading or trailing whitespace."]
    assert "newline" in value_warnings("a\nb")[0]
    assert not value_warnings("clean")


def test_secret_map_ref_normalizes_folder():
    ref = SecretMapRef("os-keyring", "/my-app/", "dev")
    assert ref.folder == "my-app"
    assert ref.path == "/my-app/dev"


def test_secret_map_is_secret_key():
    sm = SecretMap(
        backend="os-keyring",
        folder="f",
        name="n",
        values={"A": "1", "HOST": "x"},
        non_secret_keys=["HOST"],
    )
    assert sm.is_secret_key("A")
    assert not sm.is_secret_key("HOST")
    assert sm.keys == ["A", "HOST"]
