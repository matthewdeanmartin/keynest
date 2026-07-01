"""Phase-5 secret-map tools: diff, redaction, lint, staleness, rotation, JSON I/O.

All functions here are pure (no backend or I/O side effects) so they are trivial
to test and safe to call from both the CLI and the GUI. Anything that *reads*
secret values keeps them in memory only; redaction never emits real values.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

UTC = timezone.utc

from keynest.model import ScalarValue, SecretMap, key_warning, now_iso, value_warnings

# Default age after which a secret map is considered "stale" and worth a look.
DEFAULT_STALE_DAYS = 90
# Default age after which a secret is flagged for rotation.
DEFAULT_ROTATION_DAYS = 180

REDACTED = "***REDACTED***"


# -- diff --------------------------------------------------------------------


@dataclass
class MapDiff:
    """A key-level diff between two secret maps. Never holds secret values."""

    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """Return ``True`` if any key was added, removed, or changed."""
        return bool(self.added or self.removed or self.changed)


def diff_maps(left: SecretMap, right: SecretMap) -> MapDiff:
    """Compute the key-level differences from ``left`` to ``right``.

    Values are compared to classify keys as changed/unchanged, but no values are
    stored in the result.

    Args:
        left: The baseline map.
        right: The map to compare against the baseline.

    Returns:
        A :class:`MapDiff` describing added/removed/changed/unchanged keys.
    """
    left_keys = set(left.values)
    right_keys = set(right.values)
    diff = MapDiff()
    diff.added = sorted(right_keys - left_keys)
    diff.removed = sorted(left_keys - right_keys)
    for key in sorted(left_keys & right_keys):
        if left.values[key] == right.values[key]:
            diff.unchanged.append(key)
        else:
            diff.changed.append(key)
    return diff


# -- redaction ---------------------------------------------------------------


def redact_values(secret_map: SecretMap) -> dict[str, ScalarValue]:
    """Return the map's values with secret keys replaced by a redaction marker.

    Keys explicitly marked as non-secret config are kept as-is; everything else
    becomes :data:`REDACTED`.

    Args:
        secret_map: The map to redact.

    Returns:
        A new dict safe to share or commit.
    """
    return {key: (value if not secret_map.is_secret_key(key) else REDACTED) for key, value in secret_map.values.items()}


def export_redacted_json(secret_map: SecretMap, *, indent: int = 2) -> str:
    """Serialize a redacted view of ``secret_map`` to JSON."""
    payload = {
        "path": secret_map.path,
        "backend": secret_map.backend,
        "description": secret_map.description,
        "tags": secret_map.tags,
        "values": redact_values(secret_map),
    }
    return json.dumps(payload, indent=indent, sort_keys=True)


# -- JSON import/export (full values) ----------------------------------------


def export_json(secret_map: SecretMap, *, indent: int = 2) -> str:
    """Serialize the full (non-redacted) values of a map to JSON.

    This emits real secret values; callers must treat the output as sensitive.
    """
    return json.dumps(secret_map.values, indent=indent, sort_keys=True)


def import_json(text: str) -> dict[str, ScalarValue]:
    """Parse a flat JSON object of scalar values into a values dict.

    Args:
        text: JSON text encoding an object of key -> scalar.

    Returns:
        The parsed values mapping.

    Raises:
        ValueError: If the JSON is not an object, or has non-scalar values.
    """
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object at the top level.")
    result: dict[str, ScalarValue] = {}
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            raise ValueError(f"Value for {key!r} is nested; only scalar values are supported.")
        result[key] = value
    return result


# -- lint --------------------------------------------------------------------


@dataclass
class LintFinding:
    """One key-naming or value-hygiene issue found while linting a map."""

    key: str
    message: str


def lint_map(secret_map: SecretMap) -> list[LintFinding]:
    """Report Bash-name and value-hygiene issues for every key in ``secret_map``.

    Args:
        secret_map: The map to lint.

    Returns:
        A list of :class:`LintFinding`; empty if the map is clean.
    """
    findings: list[LintFinding] = []
    for key in secret_map.keys:
        warning = key_warning(key)
        if warning:
            findings.append(LintFinding(key, warning))
        for vw in value_warnings(secret_map.values[key]):
            findings.append(LintFinding(key, vw))
    return findings


# -- staleness / rotation ----------------------------------------------------


def _parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp, returning ``None`` if absent/invalid."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def age_in_days(timestamp: str | None, *, now: datetime | None = None) -> float | None:
    """Return the age of an ISO timestamp in days, or ``None`` if unparseable."""
    parsed = _parse_iso(timestamp)
    if parsed is None:
        return None
    reference = now or datetime.now(UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    return (reference - parsed).total_seconds() / 86400.0


def is_stale(
    updated_at: str | None,
    *,
    stale_days: int = DEFAULT_STALE_DAYS,
    now: datetime | None = None,
) -> bool:
    """Return ``True`` if ``updated_at`` is older than ``stale_days``.

    A missing/invalid timestamp is treated as stale (we cannot prove freshness).
    """
    age = age_in_days(updated_at, now=now)
    if age is None:
        return True
    return age >= stale_days


def needs_rotation(
    updated_at: str | None,
    *,
    rotation_days: int = DEFAULT_ROTATION_DAYS,
    now: datetime | None = None,
) -> bool:
    """Return ``True`` if a secret last updated ``updated_at`` is due for rotation."""
    age = age_in_days(updated_at, now=now)
    if age is None:
        return True
    return age >= rotation_days


# -- duplicate ---------------------------------------------------------------


def duplicate_map(secret_map: SecretMap, new_name: str, *, new_folder: str | None = None) -> SecretMap:
    """Return a copy of ``secret_map`` under a new name (and optional folder).

    Timestamps are reset so the duplicate reads as freshly created.

    Args:
        secret_map: The map to copy.
        new_name: The name for the duplicate.
        new_folder: Optional new folder; defaults to the source folder.

    Returns:
        A new :class:`SecretMap` with copied values and metadata.
    """
    return SecretMap(
        backend=secret_map.backend,
        folder=new_folder if new_folder is not None else secret_map.folder,
        name=new_name,
        values=dict(secret_map.values),
        description=secret_map.description,
        tags=list(secret_map.tags),
        non_secret_keys=list(secret_map.non_secret_keys),
        created_at=now_iso(),
    )
