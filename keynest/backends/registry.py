"""Backend selection helpers shared by the CLI and GUI."""

from __future__ import annotations

from keynest.backends.aws_secrets_manager import AwsSecretsManagerBackend
from keynest.backends.base import SecretBackend
from keynest.backends.os_keyring import OsKeyringBackend
from keynest.model import BackendId


def get_backend(
    backend_id: BackendId,
    *,
    profile: str | None = None,
    region: str | None = None,
) -> SecretBackend:
    """Return a backend instance for ``backend_id``.

    Args:
        backend_id: ``"os-keyring"`` or ``"aws-secrets-manager"``.
        profile: AWS profile (AWS backend only).
        region: AWS region (AWS backend only).

    Returns:
        A backend implementing :class:`~keynest.backends.base.SecretBackend`.

    Raises:
        ValueError: If ``backend_id`` is unknown.
    """
    if backend_id == "os-keyring":
        return OsKeyringBackend()
    if backend_id == "aws-secrets-manager":
        return AwsSecretsManagerBackend(profile=profile, region=region)
    raise ValueError(f"Unknown backend: {backend_id!r}")
