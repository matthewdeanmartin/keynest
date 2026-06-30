"""Environment diagnostics: keyring backend, platform, and store health.

Helps answer "why is my keyring weird on Linux?" and surfaces the locations and
sizes of keynest's non-secret local files. Never reads or reports secret values.
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass, field

from keynest.services.audit import default_audit_path
from keynest.services.index_store import IndexStore


@dataclass
class Diagnostics:
    """A snapshot of the local keynest environment."""

    python_version: str
    platform: str
    keyring_backend: str
    keyring_detail: str
    index_path: str
    index_exists: bool
    index_item_count: int
    audit_path: str
    audit_exists: bool
    notes: list[str] = field(default_factory=list)

    def as_lines(self) -> list[str]:
        """Render the diagnostics as human-readable ``key: value`` lines."""
        lines = [
            f"python: {self.python_version}",
            f"platform: {self.platform}",
            f"keyring backend: {self.keyring_backend}",
            f"keyring detail: {self.keyring_detail}",
            f"index: {self.index_path} (exists={self.index_exists}, items={self.index_item_count})",
            f"audit log: {self.audit_path} (exists={self.audit_exists})",
        ]
        lines.extend(f"note: {note}" for note in self.notes)
        return lines


def _keyring_info() -> tuple[str, str, list[str]]:
    """Return ``(backend_name, detail, notes)`` for the active keyring backend."""
    notes: list[str] = []
    try:
        # Imported lazily so diagnostics degrade gracefully if keyring is absent.
        import keyring  # pylint: disable=import-outside-toplevel
    except ImportError:
        return "unavailable", "keyring is not installed", notes

    backend = keyring.get_keyring()
    name = backend.__class__.__name__
    detail = getattr(backend, "name", name)

    # Common Linux pain point: headless/SSH sessions fall back to a backend that
    # can't actually persist anything.
    if "fail" in name.lower():
        notes.append(
            "Active keyring is a fail/null backend; no OS credential store was found. "
            "On Linux install gnome-keyring or KDE Wallet (and run a session bus), "
            "or set the keyring backend explicitly."
        )
    if sys.platform.startswith("linux") and "secretservice" not in name.lower() and "kwallet" not in name.lower():
        notes.append(
            "On Linux, the SecretService (gnome-keyring) or KWallet backend is recommended for persistent storage."
        )
    return name, str(detail), notes


def collect(index: IndexStore | None = None) -> Diagnostics:
    """Gather environment diagnostics.

    Args:
        index: An optional index store (default: the standard location).

    Returns:
        A populated :class:`Diagnostics`.
    """
    store = index or IndexStore()
    backend_name, detail, notes = _keyring_info()

    index_path = store.path
    index_exists = index_path.exists()
    item_count = 0
    if index_exists:
        try:
            store.load()
            item_count = len(store.items())
        except (ValueError, OSError) as exc:
            notes.append(f"Index file could not be read: {exc}")

    audit_path = default_audit_path()

    return Diagnostics(
        python_version=platform.python_version(),
        platform=platform.platform(),
        keyring_backend=backend_name,
        keyring_detail=detail,
        index_path=str(index_path),
        index_exists=index_exists,
        index_item_count=item_count,
        audit_path=str(audit_path),
        audit_exists=audit_path.exists(),
        notes=notes,
    )
