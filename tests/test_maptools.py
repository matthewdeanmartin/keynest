"""Tests for the Phase-5 maptools service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from keynest.model import SecretMap
from keynest.services import maptools


def _map(name="m", **values) -> SecretMap:
    return SecretMap(backend="os-keyring", folder="f", name=name, values=values)


def test_diff_classifies_keys():
    left = _map(A="1", B="2", C="3")
    right = _map(B="2", C="9", D="4")
    diff = maptools.diff_maps(left, right)
    assert diff.added == ["D"]
    assert diff.removed == ["A"]
    assert diff.changed == ["C"]
    assert diff.unchanged == ["B"]
    assert diff.has_changes


def test_diff_identical_has_no_changes():
    left = _map(A="1")
    right = _map(A="1")
    assert not maptools.diff_maps(left, right).has_changes


def test_redact_keeps_non_secret_config():
    sm = SecretMap(
        backend="os-keyring",
        folder="f",
        name="m",
        values={"PASSWORD": "hunter2", "HOST": "localhost"},
        non_secret_keys=["HOST"],
    )
    redacted = maptools.redact_values(sm)
    assert redacted == {"PASSWORD": maptools.REDACTED, "HOST": "localhost"}


def test_export_redacted_json_has_no_real_secret():
    sm = _map(PASSWORD="hunter2")
    out = maptools.export_redacted_json(sm)
    assert "hunter2" not in out
    assert maptools.REDACTED in out


def test_import_json_roundtrip():
    text = maptools.export_json(_map(A="1", B="2"))
    assert maptools.import_json(text) == {"A": "1", "B": "2"}


def test_import_json_rejects_nested():
    with pytest.raises(ValueError):
        maptools.import_json('{"A": {"nested": 1}}')


def test_import_json_rejects_non_object():
    with pytest.raises(ValueError):
        maptools.import_json("[1, 2, 3]")


def test_lint_flags_bad_key():
    findings = maptools.lint_map(_map(**{"bad-key": "v"}))
    assert any(f.key == "bad-key" for f in findings)


def test_lint_clean_map():
    assert not maptools.lint_map(_map(GOOD_KEY="v"))


def test_lint_flags_value_whitespace():
    findings = maptools.lint_map(_map(TOKEN=" trailing "))
    assert any("whitespace" in f.message for f in findings)


def test_age_and_staleness():
    now = datetime(2026, 6, 29, tzinfo=UTC)
    old = (now - timedelta(days=100)).isoformat()
    fresh = (now - timedelta(days=5)).isoformat()
    assert maptools.age_in_days(old, now=now) == pytest.approx(100, abs=0.01)
    assert maptools.is_stale(old, stale_days=90, now=now)
    assert not maptools.is_stale(fresh, stale_days=90, now=now)


def test_missing_timestamp_is_stale_and_needs_rotation():
    assert maptools.is_stale(None)
    assert maptools.needs_rotation(None)


def test_needs_rotation_threshold():
    now = datetime(2026, 6, 29, tzinfo=UTC)
    old = (now - timedelta(days=200)).isoformat()
    assert maptools.needs_rotation(old, rotation_days=180, now=now)
    young = (now - timedelta(days=10)).isoformat()
    assert not maptools.needs_rotation(young, rotation_days=180, now=now)


def test_duplicate_copies_values_and_resets_created():
    source = _map(name="orig", A="1", B="2")
    source.created_at = "2020-01-01T00:00:00+00:00"
    copy = maptools.duplicate_map(source, "clone", new_folder="other")
    assert copy.name == "clone"
    assert copy.folder == "other"
    assert copy.values == {"A": "1", "B": "2"}
    # Mutating the copy must not affect the source.
    copy.values["A"] = "changed"
    assert source.values["A"] == "1"
    assert copy.created_at != source.created_at
