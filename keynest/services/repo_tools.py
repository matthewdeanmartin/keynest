"""Repo hygiene helpers: scan for ``.env`` files and suggest ``.gitignore`` lines."""

from __future__ import annotations

from pathlib import Path

# Filenames that commonly contain secrets and should not be committed.
SUSPICIOUS_GLOBS = ["*.env", ".env", ".env.*", "*.pem", "*.key", "credentials", "*.secrets"]

GITIGNORE_SUGGESTIONS = [
    ".env",
    ".env.*",
    "!.env.example",
    "*.pem",
    "*.key",
    ".devsecrets/",
]


def scan_for_env_files(folder: str, max_results: int = 200) -> list[str]:
    """Return paths of likely-secret files found under ``folder`` (recursive).

    Skips common vendor/VCS directories. Returns at most ``max_results`` paths.

    Args:
        folder: Directory to scan.
        max_results: Maximum number of paths to return.

    Returns:
        A sorted list of matching file paths (as strings).
    """
    root = Path(folder)
    if not root.is_dir():
        return []
    skip_dirs = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"}
    found: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        name = path.name
        if (
            name == ".env"
            or name.startswith(".env.")
            or name.endswith((".env", ".pem", ".key", ".secrets"))
            or name == "credentials"
        ):
            found.add(str(path))
            if len(found) >= max_results:
                break
    return sorted(found)


def gitignore_suggestions(existing: str = "") -> list[str]:
    """Return ``.gitignore`` lines not already present in ``existing`` content."""
    present = {line.strip() for line in existing.splitlines()}
    return [line for line in GITIGNORE_SUGGESTIONS if line not in present]
