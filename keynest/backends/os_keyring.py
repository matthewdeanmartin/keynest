"""OS keyring backend.

Secret maps are stored as JSON payloads in the OS credential store via the
``keyring`` package:

    service_name = "DeveloperSecretWorkbench"
    username     = "/folder/name"
    password     = json.dumps(values)

Where the active keyring backend supports enumeration (see
:mod:`keynest.backends.keyring_enumerate`), the keyring itself is the source of
truth for *which* maps exist. A non-secret
:class:`~keynest.services.index_store.IndexStore` supplies the metadata the
keyring cannot recover (descriptions, tags, key names, timestamps) and serves
listing on backends that cannot enumerate.
"""

from __future__ import annotations

import contextlib
import json
import logging

import keyring
from keyring.errors import KeyringError

from keynest.backends import keyring_enumerate
from keynest.backends.base import (
    BackendStatus,
    SecretMapExists,
    SecretMapNotFound,
)
from keynest.model import (
    SERVICE_NAME_HINT,
    BackendId,
    RawCredential,
    SecretMap,
    SecretMapRef,
    logical_path,
    normalize_folder,
    now_iso,
    parse_path,
)
from keynest.services.index_store import IndexStore

log = logging.getLogger(__name__)

SERVICE_NAME = SERVICE_NAME_HINT


class OsKeyringBackend:
    """Stores secret maps in the OS credential store, indexed locally."""

    backend_id: BackendId = "os-keyring"

    def __init__(self, index: IndexStore | None = None) -> None:
        """Create the backend with an optional pre-built index store."""
        self.index = index or IndexStore()

    # -- internal helpers ----------------------------------------------------

    @staticmethod
    def _username(folder: str, name: str) -> str:
        return logical_path(folder, name)

    def _read_payload(self, folder: str, name: str) -> str | None:
        return keyring.get_password(SERVICE_NAME, self._username(folder, name))

    def _enumerate_refs(self) -> list[SecretMapRef] | None:
        """Return the maps that actually exist in the keyring, or ``None``.

        The active keyring backend is the source of truth for *existence*: we
        enumerate its credentials, keep those stored under our service name, and
        parse each ``/folder/name`` username back into a reference. Returns
        ``None`` if the backend cannot enumerate, so callers can fall back to
        the index.
        """
        try:
            creds = list(keyring_enumerate.list_credentials(keyring.get_keyring()))
        except keyring_enumerate.EnumerationNotSupported:
            return None
        except Exception:  # pylint: disable=broad-exception-caught
            log.exception("Keyring enumeration failed; falling back to index.")
            return None

        refs: list[SecretMapRef] = []
        for cred in creds:
            if cred.service != SERVICE_NAME or not cred.username:
                continue
            try:
                folder, name = parse_path(cred.username)
            except ValueError:
                continue
            refs.append(SecretMapRef(self.backend_id, folder, name))
        return refs

    def list_raw_credentials(self) -> list[RawCredential]:
        """Return all OS credentials *not* managed by keynest (names only).

        This surfaces entries created by other apps (git, AWS CLI, etc.) so a UI
        can show the full credential store read-only. Only ``(service, username)``
        is read; secret values are never fetched or decrypted. keynest's own
        maps are excluded (they are served by :meth:`list_secret_maps`).

        Returns an empty list when the active backend cannot be enumerated.
        """
        try:
            creds = list(keyring_enumerate.list_credentials(keyring.get_keyring()))
        except keyring_enumerate.EnumerationNotSupported:
            return []
        except Exception:  # pylint: disable=broad-exception-caught
            log.exception("Keyring enumeration failed; cannot list raw credentials.")
            return []

        raw = [
            RawCredential(service=cred.service, username=cred.username or None)
            for cred in creds
            if cred.service and cred.service != SERVICE_NAME
        ]
        return sorted(raw, key=lambda c: (c.service, c.username or ""))

    # -- SecretBackend protocol ----------------------------------------------

    def list_folders(self) -> list[str]:
        """Return all known folder names, always including ``default``."""
        folders = {ref.folder for ref in self.list_secret_maps()}
        folders.add("default")
        # Preserve index-only folders (e.g. empty folders the index records).
        folders.update(self.index.folders())
        return sorted(folders)

    def list_secret_maps(self, folder: str | None = None) -> list[SecretMapRef]:
        """Return references for stored maps, optionally filtered by folder.

        When the keyring can be enumerated, its contents are authoritative for
        which maps exist; otherwise listing falls back to the local index.
        """
        wanted = normalize_folder(folder) if folder else None

        enumerated = self._enumerate_refs()
        if enumerated is not None:
            refs = enumerated
        else:
            refs = [
                SecretMapRef(self.backend_id, item.folder, item.name)
                for item in self.index.items()
                if item.backend == self.backend_id
            ]

        result = [r for r in refs if wanted is None or r.folder == wanted]
        return sorted(result, key=lambda r: (r.folder, r.name))

    def get_secret_map(self, folder: str, name: str) -> SecretMap:
        """Load a secret map, merging values from the keyring with index metadata."""
        folder = normalize_folder(folder)
        payload = self._read_payload(folder, name)
        if payload is None:
            raise SecretMapNotFound(folder, name)
        values = json.loads(payload)
        item = self.index.get(folder, name)
        return SecretMap(
            backend=self.backend_id,
            folder=folder,
            name=name,
            values=values,
            description=item.description if item else "",
            tags=list(item.tags) if item else [],
            non_secret_keys=list(item.non_secret_keys) if item else [],
            created_at=item.created_at if item else None,
            updated_at=item.updated_at if item else None,
        )

    def put_secret_map(self, secret_map: SecretMap) -> None:
        """Create or overwrite a secret map and update the index."""
        secret_map.folder = normalize_folder(secret_map.folder)
        if secret_map.created_at is None:
            secret_map.created_at = now_iso()
        secret_map.updated_at = now_iso()
        keyring.set_password(
            SERVICE_NAME,
            self._username(secret_map.folder, secret_map.name),
            json.dumps(secret_map.values),
        )
        self.index.upsert(secret_map)
        self.index.save()

    def create_secret_map(self, secret_map: SecretMap) -> None:
        """Like :meth:`put_secret_map` but fail if the map already exists."""
        if self._read_payload(secret_map.folder, secret_map.name) is not None:
            raise SecretMapExists(f"Secret map already exists: {secret_map.path}")
        self.put_secret_map(secret_map)

    def delete_secret_map(self, folder: str, name: str) -> None:
        """Delete a secret map from the keyring and index."""
        folder = normalize_folder(folder)
        if self._read_payload(folder, name) is None:
            raise SecretMapNotFound(folder, name)
        with contextlib.suppress(KeyringError):
            keyring.delete_password(SERVICE_NAME, self._username(folder, name))
        self.index.remove(folder, name)
        self.index.save()

    def rename_secret_map(self, old: SecretMapRef, new: SecretMapRef) -> None:
        """Move a secret map to a new folder/name, preserving values and metadata."""
        current = self.get_secret_map(old.folder, old.name)
        if self._read_payload(new.folder, new.name) is not None and (new.folder, new.name) != (
            old.folder,
            old.name,
        ):
            raise SecretMapExists(f"Secret map already exists: {new.path}")
        moved = SecretMap(
            backend=self.backend_id,
            folder=new.folder,
            name=new.name,
            values=current.values,
            description=current.description,
            tags=current.tags,
            non_secret_keys=current.non_secret_keys,
            created_at=current.created_at,
        )
        keyring.set_password(SERVICE_NAME, self._username(new.folder, new.name), json.dumps(moved.values))
        if (old.folder, old.name) != (new.folder, new.name):
            with contextlib.suppress(KeyringError):
                keyring.delete_password(SERVICE_NAME, self._username(old.folder, old.name))
        self.index.rename(old, new)
        self.index.upsert(moved)
        self.index.save()

    def test_connection(self) -> BackendStatus:
        """Probe the keyring backend with a round-trip on a throwaway key."""
        try:
            backend_name = keyring.get_keyring().__class__.__name__
            probe_user = "/__keynest_healthcheck__/probe"
            keyring.set_password(SERVICE_NAME, probe_user, "ok")
            value = keyring.get_password(SERVICE_NAME, probe_user)
            with contextlib.suppress(KeyringError):
                keyring.delete_password(SERVICE_NAME, probe_user)
            if value != "ok":
                return BackendStatus(self.backend_id, False, "Round-trip mismatch.")
            return BackendStatus(self.backend_id, True, f"Using {backend_name}.")
        except KeyringError as exc:
            return BackendStatus(self.backend_id, False, str(exc))
