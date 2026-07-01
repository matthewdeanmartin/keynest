"""Detect the git repository keynest is running inside, for folder defaulting.

keynest can transparently default a secret map's *folder* to the identity of the
repository the user is working in (see ``spec/transparent_relocation.md``). This
module resolves that identity as a :class:`RepoContext`.

Critical: this changes only which folder keynest *defaults* to; it never stores
secret material in the repo and never writes to the working tree. The inputs
(``.git/config``, an optional ``.keynest`` marker) are non-secret, parsed as
data only. Detection is fail-safe: any error degrades to "no repo detected".
"""

from __future__ import annotations

import configparser
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from keynest.model import normalize_folder

# Hosts we recognize as code-forge remotes. Unknown hosts (self-hosted GitLab,
# GHE, Gitea, ...) are still used verbatim; this set only drives display hints.
_KNOWN_FORGES = {"github.com", "gitlab.com", "bitbucket.org"}

# SSH scp-style remote: ``git@host:owner/repo.git`` (owner may contain '/').
_SSH_RE = re.compile(r"^[^@]+@(?P<host>[^:]+):(?P<path>.+)$")

# The optional committed marker file at a repo root. It is secret-FREE by design:
# only these keys are allowed, and none of them can hold a secret value.
MARKER_FILENAME = ".keynest"
PYPROJECT_FILENAME = "pyproject.toml"
PYPROJECT_TOOL_SECTION = "keynest"
_MARKER_ALLOWED_KEYS = {"folder", "default_map"}


class MarkerError(ValueError):
    """Raised when a ``.keynest`` marker file is present but invalid."""


@dataclass(frozen=True)
class RepoContext:
    """The identity of the git repo keynest is running inside (non-secret)."""

    root: Path
    host: str | None = None
    owner: str | None = None
    repo: str | None = None
    remote_url: str | None = None
    source: Literal["marker", "remote", "local-dir"] = "local-dir"
    # From a ``.keynest`` marker file, when present and valid.
    marker_folder: str | None = None
    default_map: str | None = None

    @property
    def is_repo(self) -> bool:
        """Whether a repository was detected at all."""
        return self.root is not None

    @property
    def slug(self) -> str | None:
        """A human display slug: the marker folder, else ``owner/repo``/``repo``."""
        if self.marker_folder:
            return self.marker_folder
        if self.repo is None:
            return None
        return f"{self.owner}/{self.repo}" if self.owner else self.repo

    @property
    def default_folder(self) -> str:
        """The folder keynest should default to for this repo.

        An explicit ``.keynest`` marker wins. Otherwise a single-segment
        ``owner.repo`` (or ``repo``) token is used so it fits the existing folder
        model without changing ``parse_path`` semantics, falling back to the
        working-tree directory name when identity is unknown.
        """
        if self.marker_folder:
            return normalize_folder(self.marker_folder)
        return folder_for_repo(self.owner, self.repo, self.root)


def folder_for_repo(owner: str | None, repo: str | None, root: Path | None) -> str:
    """Return the default folder token for a repo identity.

    ``owner``/``repo`` from a remote produce ``owner.repo``; ``repo`` alone
    produces ``repo``; otherwise the directory name of ``root`` is used. The
    result is normalized to keynest's folder rules.
    """
    if repo:
        # Owner may itself contain '/' for GitLab subgroups; flatten to dots so
        # the folder stays a single segment (v1 keeps parse_path unchanged).
        token = f"{owner}.{repo}".replace("/", ".") if owner else repo
        return normalize_folder(_sanitize_segment(token))
    if root is not None:
        return normalize_folder(_sanitize_segment(root.name))
    return normalize_folder(None)


def _sanitize_segment(text: str) -> str:
    """Reduce a raw identity token to a safe, display-friendly folder segment."""
    # Collapse whitespace and drop characters that would confuse the keyring
    # username convention or the logical path. Keep dots/hyphens/underscores.
    cleaned = re.sub(r"\s+", "-", text.strip())
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "-", cleaned)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-.")
    return cleaned


def find_repo_root(start: Path | None = None) -> Path | None:
    """Walk up from ``start`` (default: cwd) to the nearest git working tree.

    Returns the directory containing ``.git`` (dir or file), or ``None`` if none
    is found before the filesystem root.
    """
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def _git_dir(root: Path) -> Path | None:
    """Resolve the actual git directory for ``root``.

    Handles the common case (``.git`` directory) and the worktree/submodule case
    (``.git`` is a file containing ``gitdir: <path>``). Returns ``None`` if it
    cannot be resolved.
    """
    dot_git = root / ".git"
    if dot_git.is_dir():
        return dot_git
    if dot_git.is_file():
        try:
            text = dot_git.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        prefix = "gitdir:"
        if text.startswith(prefix):
            pointer = text[len(prefix) :].strip()
            resolved = (root / pointer).resolve() if not Path(pointer).is_absolute() else Path(pointer)
            return resolved if resolved.exists() else None
    return None


def _read_remote_url(git_dir: Path) -> str | None:
    """Return the preferred remote URL from ``<git_dir>/config``, or ``None``.

    Prefers ``origin``; otherwise the first remote found. Parsed as data via
    ``configparser`` — no ``git`` subprocess, no alias/hook execution.
    """
    config_path = git_dir / "config"
    if not config_path.is_file():
        return None
    parser = configparser.ConfigParser()
    try:
        # git config allows section names with quotes; read leniently.
        parser.read_string(config_path.read_text(encoding="utf-8"))
    except (configparser.Error, OSError, UnicodeDecodeError):
        return None

    remotes: dict[str, str] = {}
    for section in parser.sections():
        # Section header looks like: [remote "origin"]
        match = re.match(r'remote "(?P<name>.+)"', section)
        if match and parser.has_option(section, "url"):
            remotes[match.group("name")] = parser.get(section, "url").strip()
    if not remotes:
        return None
    return remotes.get("origin") or next(iter(remotes.values()))


def _scrub_credentials(url: str) -> str:
    """Remove any ``user[:token]@`` credentials from an HTTPS-style remote URL."""
    return re.sub(r"(https?://)[^/@]+@", r"\1", url)


def parse_remote_url(url: str) -> tuple[str | None, str | None, str | None]:
    """Parse a git remote URL into ``(host, owner, repo)``.

    Handles SSH scp-style (``git@host:owner/repo.git``) and HTTP(S) forms, plus
    GitLab subgroups (``owner`` may contain ``/``). Returns ``(None, None,
    None)`` if it cannot be parsed. Credentials in the URL are ignored.
    """
    url = url.strip()
    host: str | None = None
    path: str | None = None

    if "://" in url:
        # scheme://[user@]host[:port]/owner/.../repo(.git)
        scheme, after_scheme = url.split("://", 1)
        after_scheme = after_scheme.split("@", 1)[-1]  # drop credentials
        if "/" not in after_scheme:
            return None, None, None
        host_part, path = after_scheme.split("/", 1)
        host = host_part.split(":", 1)[0]  # drop :port
        if not host or scheme.lower() == "file":
            return None, None, None
    elif (ssh := _SSH_RE.match(url)) is not None:
        # scp-style: git@host:owner/repo.git (no explicit scheme)
        host = ssh.group("host")
        path = ssh.group("path")
    else:
        return None, None, None

    if not path:
        return host_normalized(host), None, None

    path = path.strip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")]
    segments = [seg for seg in path.split("/") if seg]
    if not segments:
        return host_normalized(host), None, None
    repo = segments[-1]
    owner = "/".join(segments[:-1]) or None
    return host_normalized(host), owner, repo


def host_normalized(host: str | None) -> str | None:
    """Lowercase a host name; return ``None`` unchanged."""
    return host.lower() if host else None


def validate_marker(data: dict[str, object]) -> tuple[str, str | None]:
    """Validate parsed ``.keynest`` contents; return ``(folder, default_map)``.

    Enforces the secret-free schema: only ``folder`` (required, str) and
    ``default_map`` (optional, str) are permitted. Any other key is rejected so
    the file can never be abused to smuggle a secret value.

    Raises:
        MarkerError: If the schema is violated.
    """
    unknown = set(data) - _MARKER_ALLOWED_KEYS
    if unknown:
        raise MarkerError(
            f"Unknown key(s) in {MARKER_FILENAME}: {', '.join(sorted(unknown))}. "
            f"Only {sorted(_MARKER_ALLOWED_KEYS)} are allowed (no secret values)."
        )
    folder = data.get("folder")
    if not isinstance(folder, str) or not folder.strip():
        raise MarkerError(f"{MARKER_FILENAME} must set a non-empty string 'folder'.")
    default_map = data.get("default_map")
    if default_map is not None and (not isinstance(default_map, str) or not default_map.strip()):
        raise MarkerError(f"{MARKER_FILENAME} 'default_map' must be a non-empty string.")
    return folder.strip(), (default_map.strip() if isinstance(default_map, str) else None)


def read_marker(root: Path) -> tuple[str, str | None] | None:
    """Read and validate ``<root>/.keynest``; return ``(folder, default_map)``.

    Returns ``None`` if the file does not exist. Raises :class:`MarkerError` if
    the file is present but malformed or violates the secret-free schema.
    """
    path = root / MARKER_FILENAME
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError) as exc:
        raise MarkerError(f"Could not parse {MARKER_FILENAME}: {exc}") from exc
    return validate_marker(data)


def read_pyproject_marker(root: Path) -> tuple[str, str | None] | None:
    """Read and validate ``<root>/pyproject.toml`` ``[tool.keynest]`` section.

    Returns ``(folder, default_map)`` when the section is present and valid.
    Returns ``None`` if ``pyproject.toml`` does not exist or has no
    ``[tool.keynest]`` section. Raises :class:`MarkerError` if the section is
    present but violates the secret-free schema.
    """
    path = root / PYPROJECT_FILENAME
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError) as exc:
        raise MarkerError(f"Could not parse {PYPROJECT_FILENAME}: {exc}") from exc
    section = data.get("tool", {}).get(PYPROJECT_TOOL_SECTION)
    if section is None:
        return None
    if not isinstance(section, dict):
        raise MarkerError(f"[tool.{PYPROJECT_TOOL_SECTION}] in {PYPROJECT_FILENAME} must be a table.")
    return validate_marker(section)


def write_marker(root: Path, folder: str, default_map: str | None = None) -> Path:
    """Write a ``.keynest`` marker at ``root``; return its path.

    The written file is secret-free by construction: only ``folder`` and an
    optional ``default_map`` are serialized, and the values are validated to be
    plain folder/name tokens. This function *cannot* write a secret value —
    there is no field for one, and inputs are validated first.

    Raises:
        MarkerError: If ``folder``/``default_map`` are invalid.
    """
    # Validate through the same gate as reading, so writer and reader agree.
    payload: dict[str, object] = {"folder": folder}
    if default_map is not None:
        payload["default_map"] = default_map
    validated_folder, validated_map = validate_marker(payload)

    lines = [
        "# keynest repo marker — safe to commit; contains NO secret values.",
        "# It only maps this repo to a keynest folder. See `keynest init-repo`.",
        f"folder = {_toml_str(validated_folder)}",
    ]
    if validated_map is not None:
        lines.append(f"default_map = {_toml_str(validated_map)}")
    path = root / MARKER_FILENAME
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _toml_str(value: str) -> str:
    """Serialize a string as a TOML basic string (escaping quotes/backslashes)."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def detect(start: Path | None = None) -> RepoContext | None:
    """Detect the repository context at ``start`` (default: cwd).

    Resolution order:

    1. ``[tool.keynest]`` in ``pyproject.toml`` at the repository root.
    2. An explicit ``.keynest`` marker file at the repository root.
    3. The git remote URL (``origin`` preferred).
    4. The working-tree directory name.

    Returns ``None`` if not inside a git repo. Never raises: any failure reading
    git metadata degrades to a local-dir context. A malformed marker is ignored
    (falls through to the next source) rather than crashing detection.
    """
    try:
        root = find_repo_root(start)
    except OSError:
        return None
    if root is None:
        return None

    # 1. pyproject.toml [tool.keynest] takes priority.
    try:
        marker = read_pyproject_marker(root)
    except MarkerError:
        marker = None
    if marker is not None:
        folder, default_map = marker
        return RepoContext(
            root=root,
            source="marker",
            marker_folder=folder,
            default_map=default_map,
        )

    # 2. Explicit .keynest marker file overrides inferred identity.
    try:
        marker = read_marker(root)
    except MarkerError:
        marker = None
    if marker is not None:
        folder, default_map = marker
        return RepoContext(
            root=root,
            source="marker",
            marker_folder=folder,
            default_map=default_map,
        )

    # 3. Git remote identity.
    git_dir = None
    remote_url = None
    try:
        git_dir = _git_dir(root)
        if git_dir is not None:
            remote_url = _read_remote_url(git_dir)
    except OSError:
        remote_url = None

    if remote_url:
        host, owner, repo = parse_remote_url(remote_url)
        if repo:
            return RepoContext(
                root=root,
                host=host,
                owner=owner,
                repo=repo,
                remote_url=_scrub_credentials(remote_url),
                source="remote",
            )

    # 4. No usable remote: identify by the working-tree directory name.
    return RepoContext(root=root, source="local-dir")


def is_known_forge(host: str | None) -> bool:
    """Whether ``host`` is a recognized public code forge (display hint only)."""
    return host_normalized(host) in _KNOWN_FORGES
