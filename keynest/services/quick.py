"""Low-friction creation helpers shared by the GUI (and usable from the CLI).

These wrap the backend so the Tk dialogs stay thin and the logic is testable
without a display.
"""

from __future__ import annotations

from keynest.backends.base import SecretBackend, SecretMapNotFound
from keynest.model import BackendId, SecretMap, parse_path
from keynest.services.dotenv_parser import DotenvParseResult, parse_dotenv

# The single key name used when storing a "named password" as a secret map.
DEFAULT_VALUE_KEY = "VALUE"


def quick_create_password(
    backend: SecretBackend,
    name: str,
    value: str,
    *,
    backend_id: BackendId = "os-keyring",
    folder: str = "default",
    key: str = DEFAULT_VALUE_KEY,
) -> SecretMap:
    """Create (or overwrite) a single-key secret map: ``/folder/name`` -> ``{key: value}``.

    This is the fast path for "I just want to save FOO=xyzzy" without choosing a
    folder or building a multi-key map.

    Args:
        backend: The backend to persist into.
        name: The secret map name (also the human-facing password name).
        value: The secret value.
        backend_id: Which backend the map belongs to.
        folder: Destination folder (defaults to ``default``).
        key: The key name to store the value under.

    Returns:
        The persisted :class:`SecretMap`.

    Raises:
        ValueError: If ``name`` is blank.
    """
    if not name.strip():
        raise ValueError("Name must not be empty.")
    secret_map = SecretMap(backend=backend_id, folder=folder, name=name.strip(), values={key: value})
    backend.put_secret_map(secret_map)
    return secret_map


def preview_env(text: str) -> DotenvParseResult:
    """Parse pasted ``.env``-style text into values + warnings (no side effects)."""
    return parse_dotenv(text)


def bulk_set_from_env(
    backend: SecretBackend,
    path: str,
    text: str,
    *,
    backend_id: BackendId = "os-keyring",
) -> tuple[SecretMap, DotenvParseResult]:
    """Parse ``.env`` text and merge it into the map at ``path``, creating if needed.

    Args:
        backend: The backend to read/write.
        path: ``folder/name`` (or bare ``name``) target.
        text: Pasted ``.env``-style content.
        backend_id: Backend to use when creating a new map.

    Returns:
        A tuple of the saved :class:`SecretMap` and the parse result (for warnings).

    Raises:
        ValueError: If parsing yields no usable keys, or the path has no name.
    """
    folder, name = parse_path(path)
    result = parse_dotenv(text)
    if not result.values:
        raise ValueError("No KEY=value pairs were found in the pasted text.")
    try:
        secret_map = backend.get_secret_map(folder, name)
    except SecretMapNotFound:
        secret_map = SecretMap(backend=backend_id, folder=folder, name=name)
    secret_map.values.update(result.values)
    backend.put_secret_map(secret_map)
    return secret_map, result
