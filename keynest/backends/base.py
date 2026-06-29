"""The :class:`SecretBackend` protocol and shared backend types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from keynest.model import BackendId, SecretMap, SecretMapRef


@dataclass
class BackendStatus:
    """The result of a backend connectivity check."""

    backend: BackendId
    ok: bool
    detail: str = ""


class BackendError(Exception):
    """Base class for backend errors."""


class SecretMapNotFound(BackendError):
    """Raised when a requested secret map does not exist."""

    def __init__(self, folder: str, name: str) -> None:
        """Record the missing map's folder and name."""
        super().__init__(f"Secret map not found: /{folder}/{name}")
        self.folder = folder
        self.name = name


class SecretMapExists(BackendError):
    """Raised when creating a secret map that already exists."""


@runtime_checkable
class SecretBackend(Protocol):
    """A storage backend for secret maps.

    Implementations persist :class:`~keynest.model.SecretMap` objects keyed by
    ``(folder, name)`` and never expose secret values through listing APIs.
    """

    backend_id: BackendId

    def list_folders(self) -> list[str]:
        """Return all known folder names (always including ``default``)."""

    def list_secret_maps(self, folder: str | None = None) -> list[SecretMapRef]:
        """Return references for all secret maps, optionally filtered by folder."""

    def get_secret_map(self, folder: str, name: str) -> SecretMap:
        """Load a full secret map including its values.

        Raises:
            SecretMapNotFound: If the map does not exist.
        """

    def put_secret_map(self, secret_map: SecretMap) -> None:
        """Create or overwrite a secret map."""

    def delete_secret_map(self, folder: str, name: str) -> None:
        """Delete a secret map.

        Raises:
            SecretMapNotFound: If the map does not exist.
        """

    def rename_secret_map(self, old: SecretMapRef, new: SecretMapRef) -> None:
        """Rename/move a secret map from ``old`` to ``new``."""

    def test_connection(self) -> BackendStatus:
        """Check that the backend is reachable and usable."""
