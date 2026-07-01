"""Core data model: secret maps, references, and validation.

A *secret map* is a dictionary of string keys to JSON-compatible scalar values.
Each map is identified by a ``(backend, folder, name)`` triple. The canonical
logical path is ``/folder/name``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

# JSON-compatible scalar values tolerated in a secret map payload.
ScalarValue = str | int | float | bool | None

BackendId = Literal["os-keyring", "aws-secrets-manager"]

DEFAULT_FOLDER = "default"

# The keyring service name under which all secret maps are stored. Exposed here
# so generated code snippets and the backend agree on a single literal.
SERVICE_NAME_HINT = "DeveloperSecretWorkbench"

# A POSIX/Bash-compatible environment variable name.
_BASH_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def normalize_folder(folder: str | None) -> str:
    """Normalize a folder name to its bare form (no leading/trailing slashes).

    Args:
        folder: A folder name such as ``"my-app"``, ``"/my-app"``, or ``None``.

    Returns:
        The normalized folder name. Empty or ``None`` becomes :data:`DEFAULT_FOLDER`.
    """
    if not folder:
        return DEFAULT_FOLDER
    cleaned = folder.strip().strip("/").strip()
    return cleaned or DEFAULT_FOLDER


def logical_path(folder: str, name: str) -> str:
    """Return the canonical ``/folder/name`` path for a secret map."""
    return f"/{normalize_folder(folder)}/{name}"


def parse_path(path: str) -> tuple[str, str]:
    """Parse a ``folder/name`` or ``/folder/name`` path into ``(folder, name)``.

    A bare ``name`` with no slash is placed in the default folder.

    Args:
        path: A logical path like ``"my-app/dev"`` or ``"/my-app/dev"``.

    Returns:
        A ``(folder, name)`` tuple.

    Raises:
        ValueError: If ``name`` is empty.
    """
    stripped = path.strip()
    had_trailing_slash = stripped.endswith("/")
    cleaned = stripped.strip("/")
    if "/" in cleaned:
        folder, _, name = cleaned.partition("/")
    elif had_trailing_slash:
        # A trailing slash signals "folder/<missing name>", which is invalid.
        folder, name = cleaned, ""
    else:
        folder, name = DEFAULT_FOLDER, cleaned
    folder = normalize_folder(folder)
    name = name.strip()
    if not name:
        raise ValueError(f"Secret map path has no name: {path!r}")
    return folder, name


def is_valid_bash_name(key: str) -> bool:
    """Return ``True`` if ``key`` is a valid Bash/POSIX environment variable name."""
    return bool(_BASH_NAME_RE.match(key))


def key_warning(key: str) -> str | None:
    """Return a human-readable warning if ``key`` is not Bash-compatible, else ``None``.

    Args:
        key: The candidate key name.

    Returns:
        A warning string, or ``None`` if the key is a valid Bash name.
    """
    if not key:
        return "Key name is empty."
    if is_valid_bash_name(key):
        return None
    if key[0].isdigit():
        return f"{key!r} starts with a digit; not a valid shell variable name."
    if "-" in key:
        return f"{key!r} contains a hyphen; shells cannot export it as an env var."
    return f"{key!r} is not a valid shell variable name (use letters, digits, underscore)."


def value_warnings(value: ScalarValue) -> list[str]:
    """Return a list of warnings about a secret value (e.g. stray whitespace).

    Args:
        value: The secret value to inspect.

    Returns:
        A list of warning strings; empty if nothing looks suspicious.
    """
    warnings: list[str] = []
    if isinstance(value, str):
        if value != value.strip():
            warnings.append("Value has leading or trailing whitespace.")
        if "\n" in value or "\r" in value:
            warnings.append("Value contains a newline.")
    return warnings


@dataclass(frozen=True)
class SecretMapRef:
    """An identifier for a secret map, without its values."""

    backend: BackendId
    folder: str
    name: str

    def __post_init__(self) -> None:
        """Normalize the folder name in place."""
        object.__setattr__(self, "folder", normalize_folder(self.folder))

    @property
    def path(self) -> str:
        """The canonical ``/folder/name`` path."""
        return logical_path(self.folder, self.name)


@dataclass(frozen=True)
class RawCredential:
    """A non-keynest credential discovered in the OS store (names only).

    Unlike a :class:`SecretMapRef`, this is *not* a keynest-managed map: it has
    no folder/name structure and keynest cannot load or edit its value. Only the
    ``(service, username)`` identifiers are known — enumeration never reads the
    secret payload.
    """

    service: str
    username: str | None = None

    @property
    def label(self) -> str:
        """A compact display label, e.g. ``service — user``."""
        return f"{self.service} — {self.username}" if self.username else self.service


@dataclass
class SecretMap:
    """A secret map: a named dictionary of keys to JSON-compatible values."""

    backend: BackendId
    folder: str
    name: str
    values: dict[str, ScalarValue] = field(default_factory=dict)
    description: str = ""
    tags: list[str] = field(default_factory=list)
    # Keys explicitly marked as non-secret configuration rather than secrets.
    non_secret_keys: list[str] = field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        """Normalize the folder name in place."""
        self.folder = normalize_folder(self.folder)

    @property
    def ref(self) -> SecretMapRef:
        """A :class:`SecretMapRef` for this map."""
        return SecretMapRef(self.backend, self.folder, self.name)

    @property
    def path(self) -> str:
        """The canonical ``/folder/name`` path."""
        return logical_path(self.folder, self.name)

    @property
    def keys(self) -> list[str]:
        """The sorted list of key names in this map."""
        return sorted(self.values)

    def is_secret_key(self, key: str) -> bool:
        """Return ``True`` if ``key`` should be treated as a secret (masked)."""
        return key not in self.non_secret_keys


def now_iso() -> str:
    """Return the current local time as an ISO-8601 string with timezone offset."""
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")
