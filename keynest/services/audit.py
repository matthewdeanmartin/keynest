"""Local, append-only audit log of non-secret usage events.

Records *that* a key was copied/used and when, but never the value. Stored as
JSON Lines at ``~/.devsecrets/audit.log``.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from keynest.model import now_iso


def default_audit_path() -> Path:
    """Return the audit log path, honoring the ``DEVSECRETS_HOME`` override."""
    home = os.environ.get("DEVSECRETS_HOME")
    base = Path(home) if home else Path.home() / ".devsecrets"
    return base / "audit.log"


@dataclass
class AuditEvent:
    """A single audit record. Holds key *names*, never secret values."""

    action: str
    backend: str
    folder: str
    name: str
    key: str | None = None
    timestamp: str | None = None


class AuditLog:
    """Append-only JSON Lines audit log."""

    def __init__(self, path: Path | None = None) -> None:
        """Create an audit log backed by ``path`` (default: standard location)."""
        self.path = path or default_audit_path()

    def record(self, event: AuditEvent) -> None:
        """Append ``event`` to the log, stamping the time if absent."""
        if event.timestamp is None:
            event.timestamp = now_iso()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event)) + "\n")

    def events(self, limit: int | None = None) -> list[AuditEvent]:
        """Return recorded events, most recent last, optionally limited."""
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        if limit is not None:
            lines = lines[-limit:]
        events: list[AuditEvent] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            events.append(AuditEvent(**data))
        return events
