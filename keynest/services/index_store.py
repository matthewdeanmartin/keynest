"""Non-secret local index of OS-keyring secret maps.

The OS keyring is poor at enumeration, so keynest keeps a small JSON index at
``~/.devsecrets/index.json`` recording folders, names, key *names* (never
values), timestamps, descriptions, and tags. The index is advisory metadata;
the keyring remains the source of truth for secret values.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from keynest.model import SecretMap, SecretMapRef, normalize_folder, now_iso

INDEX_VERSION = 1


def default_index_path() -> Path:
    """Return the index file path, honoring the ``DEVSECRETS_HOME`` override."""
    home = os.environ.get("DEVSECRETS_HOME")
    base = Path(home) if home else Path.home() / ".devsecrets"
    return base / "index.json"


@dataclass
class IndexItem:
    """One entry in the local index. Never holds secret values."""

    backend: str
    folder: str
    name: str
    keys: list[str] = field(default_factory=list)
    description: str = ""
    tags: list[str] = field(default_factory=list)
    non_secret_keys: list[str] = field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class IndexStore:
    """A JSON-backed index of secret map metadata."""

    def __init__(self, path: Path | None = None) -> None:
        """Create an index store backed by ``path`` (default: standard location)."""
        self.path = path or default_index_path()
        self._items: dict[tuple[str, str], IndexItem] = {}
        self._loaded = False

    # -- persistence ---------------------------------------------------------

    def load(self) -> None:
        """Load the index from disk, tolerating a missing or empty file."""
        self._items = {}
        if self.path.exists():
            raw = self.path.read_text(encoding="utf-8").strip()
            if raw:
                data = json.loads(raw)
                for item in data.get("items", []):
                    folder = normalize_folder(item.get("folder"))
                    entry = IndexItem(
                        backend=item.get("backend", "os-keyring"),
                        folder=folder,
                        name=item["name"],
                        keys=list(item.get("keys", [])),
                        description=item.get("description", ""),
                        tags=list(item.get("tags", [])),
                        non_secret_keys=list(item.get("non_secret_keys", [])),
                        created_at=item.get("created_at"),
                        updated_at=item.get("updated_at"),
                    )
                    self._items[(folder, entry.name)] = entry
        self._loaded = True

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def save(self) -> None:
        """Atomically persist the index to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": INDEX_VERSION,
            "items": [asdict(item) for item in self._items.values()],
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    def backup(self, destination: Path | None = None) -> Path | None:
        """Copy the (non-secret) index file to a timestamped backup.

        Args:
            destination: Explicit backup path; otherwise a sibling file named
                ``index-<UTC-timestamp>.json.bak`` next to the index.

        Returns:
            The backup path, or ``None`` if there is no index file to back up.
        """
        if not self.path.exists():
            return None
        if destination is None:
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            destination = self.path.with_name(f"index-{stamp}.json.bak")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.path.read_bytes())
        return destination

    # -- queries -------------------------------------------------------------

    def items(self) -> list[IndexItem]:
        """Return all index items."""
        self._ensure_loaded()
        return list(self._items.values())

    def folders(self) -> list[str]:
        """Return all folder names referenced by the index, plus ``default``."""
        self._ensure_loaded()
        names = {item.folder for item in self._items.values()}
        names.add("default")
        return sorted(names)

    def get(self, folder: str, name: str) -> IndexItem | None:
        """Return the index item for ``(folder, name)`` or ``None``."""
        self._ensure_loaded()
        return self._items.get((normalize_folder(folder), name))

    # -- mutations -----------------------------------------------------------

    def upsert(self, secret_map: SecretMap) -> None:
        """Insert or update the index entry for ``secret_map`` (no values stored)."""
        self._ensure_loaded()
        key = (secret_map.folder, secret_map.name)
        existing = self._items.get(key)
        created = existing.created_at if existing else (secret_map.created_at or now_iso())
        self._items[key] = IndexItem(
            backend=secret_map.backend,
            folder=secret_map.folder,
            name=secret_map.name,
            keys=sorted(secret_map.values),
            description=secret_map.description,
            tags=list(secret_map.tags),
            non_secret_keys=list(secret_map.non_secret_keys),
            created_at=created,
            updated_at=now_iso(),
        )

    def remove(self, folder: str, name: str) -> None:
        """Remove the entry for ``(folder, name)`` if present."""
        self._ensure_loaded()
        self._items.pop((normalize_folder(folder), name), None)

    def rename(self, old: SecretMapRef, new: SecretMapRef) -> None:
        """Move the entry from ``old`` to ``new``, preserving metadata."""
        self._ensure_loaded()
        item = self._items.pop((old.folder, old.name), None)
        if item is None:
            return
        item.folder = new.folder
        item.name = new.name
        item.backend = new.backend
        item.updated_at = now_iso()
        self._items[(new.folder, new.name)] = item

    def add_empty_folder(self, folder: str) -> None:
        """Record an (empty) folder so it survives even with no secret maps.

        Empty folders are represented by a sentinel entry whose name is the empty
        string; :meth:`folders` derives names from items but UIs may want explicit
        empty folders. We simply ensure ``folder`` appears via a marker file-free
        approach: callers can persist a map later. This is a no-op placeholder kept
        for API symmetry; empty folders are tracked by the GUI layer separately.
        """
        # Folders only persist when they contain a secret map. Empty-folder
        # tracking is intentionally left to the UI session state to avoid
        # polluting the index with phantom entries.
        _ = normalize_folder(folder)
