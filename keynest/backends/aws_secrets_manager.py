"""AWS Secrets Manager backend.

Each secret map is stored as one AWS secret with a JSON ``SecretString`` under
the naming convention ``devsecrets/{folder}/{name}``. Maps are discovered by
filtering on the ``ManagedBy=DeveloperSecretWorkbench`` tag.

``boto3`` is imported lazily so the rest of keynest works without AWS configured.
"""

# boto3 is imported inside methods by design (AWS support is optional); broad
# excepts deliberately surface any SDK/network error as a status string.
# pylint: disable=import-outside-toplevel,broad-exception-caught

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from keynest.backends.base import BackendStatus, SecretMapExists, SecretMapNotFound
from keynest.model import BackendId, SecretMap, SecretMapRef, normalize_folder

# boto3 clients are fully dynamically typed; BaseClient only exposes generic
# meta-methods. We accept Any to avoid suppressing every call site individually.
if TYPE_CHECKING:  # pragma: no cover - typing only
    pass  # no botocore import needed now

PREFIX = "devsecrets"
MANAGED_BY = "DeveloperSecretWorkbench"
SCHEMA = "SecretMapV1"


def secret_name(folder: str, name: str) -> str:
    """Return the AWS secret name for a ``(folder, name)`` pair."""
    return f"{PREFIX}/{normalize_folder(folder)}/{name}"


def _parse_secret_name(aws_name: str) -> tuple[str, str] | None:
    """Parse ``devsecrets/folder/name`` back into ``(folder, name)`` or ``None``."""
    parts = aws_name.split("/")
    if len(parts) != 3 or parts[0] != PREFIX:
        return None
    return normalize_folder(parts[1]), parts[2]


class AwsSecretsManagerBackend:
    """Stores secret maps in AWS Secrets Manager, one secret per map."""

    backend_id: BackendId = "aws-secrets-manager"

    def __init__(
        self,
        profile: str | None = None,
        region: str | None = None,
        client: Any | None = None,
    ) -> None:
        """Create the backend, optionally with an explicit boto3 client.

        Args:
            profile: AWS profile name to use (else the default chain).
            region: AWS region name.
            client: A pre-built boto3 Secrets Manager client (mainly for tests).
        """
        self.profile = profile
        self.region = region
        self._client: Any = client

    @property
    def client(self) -> Any:
        """Return (lazily creating) the boto3 Secrets Manager client."""
        if self._client is None:
            import boto3  # imported lazily; AWS is optional

            session = boto3.session.Session(profile_name=self.profile, region_name=self.region)
            self._client = session.client("secretsmanager")
        return self._client

    # -- helpers -------------------------------------------------------------

    def _tags(self, secret_map: SecretMap) -> list[dict[str, str]]:
        return [
            {"Key": "ManagedBy", "Value": MANAGED_BY},
            {"Key": "OwnerMode", "Value": "SingleDeveloper"},
            {"Key": "Folder", "Value": secret_map.folder},
            {"Key": "Name", "Value": secret_map.name},
            {"Key": "Schema", "Value": SCHEMA},
        ]

    def _iter_managed_secrets(self) -> list[dict[str, Any]]:
        """List all AWS secrets managed by keynest."""
        paginator = self.client.get_paginator("list_secrets")
        results: list[dict[str, Any]] = []
        pages = paginator.paginate(Filters=[{"Key": "tag-key", "Values": ["ManagedBy"]}])
        for page in pages:
            for secret in page.get("SecretList", []):
                tags = {t["Key"]: t["Value"] for t in secret.get("Tags", [])}
                if tags.get("ManagedBy") == MANAGED_BY:
                    results.append(secret)
        return results

    # -- SecretBackend protocol ----------------------------------------------

    def list_folders(self) -> list[str]:
        """Return all folders that contain at least one managed secret, plus default."""
        folders = {"default"}
        for ref in self.list_secret_maps():
            folders.add(ref.folder)
        return sorted(folders)

    def list_secret_maps(self, folder: str | None = None) -> list[SecretMapRef]:
        """Return references for managed maps, optionally filtered by folder."""
        wanted = normalize_folder(folder) if folder else None
        refs: list[SecretMapRef] = []
        for secret in self._iter_managed_secrets():
            parsed = _parse_secret_name(secret.get("Name", ""))
            if parsed is None:
                continue
            fol, nam = parsed
            if wanted is not None and fol != wanted:
                continue
            refs.append(SecretMapRef(self.backend_id, fol, nam))
        return sorted(refs, key=lambda r: (r.folder, r.name))

    def get_secret_map(self, folder: str, name: str) -> SecretMap:
        """Fetch a secret map's JSON SecretString and decode it."""
        folder = normalize_folder(folder)
        try:
            response = self.client.get_secret_value(SecretId=secret_name(folder, name))
        except self.client.exceptions.ResourceNotFoundException as exc:
            raise SecretMapNotFound(folder, name) from exc
        payload = response.get("SecretString") or "{}"
        return SecretMap(
            backend=self.backend_id,
            folder=folder,
            name=name,
            values=json.loads(payload),
        )

    def put_secret_map(self, secret_map: SecretMap) -> None:
        """Create the secret if missing, otherwise overwrite its value."""
        secret_map.folder = normalize_folder(secret_map.folder)
        sid = secret_name(secret_map.folder, secret_map.name)
        body = json.dumps(secret_map.values)
        try:
            self.client.create_secret(
                Name=sid,
                SecretString=body,
                Tags=self._tags(secret_map),
            )
        except self.client.exceptions.ResourceExistsException:
            self.client.put_secret_value(SecretId=sid, SecretString=body)
            self.client.tag_resource(SecretId=sid, Tags=self._tags(secret_map))

    def create_secret_map(self, secret_map: SecretMap) -> None:
        """Create a secret map, failing if it already exists."""
        secret_map.folder = normalize_folder(secret_map.folder)
        sid = secret_name(secret_map.folder, secret_map.name)
        try:
            self.client.create_secret(
                Name=sid,
                SecretString=json.dumps(secret_map.values),
                Tags=self._tags(secret_map),
            )
        except self.client.exceptions.ResourceExistsException as exc:
            raise SecretMapExists(f"Secret map already exists: {secret_map.path}") from exc

    def delete_secret_map(self, folder: str, name: str) -> None:
        """Schedule deletion of a secret map."""
        folder = normalize_folder(folder)
        try:
            self.client.delete_secret(
                SecretId=secret_name(folder, name),
                RecoveryWindowInDays=7,
            )
        except self.client.exceptions.ResourceNotFoundException as exc:
            raise SecretMapNotFound(folder, name) from exc

    def rename_secret_map(self, old: SecretMapRef, new: SecretMapRef) -> None:
        """Rename by creating the new secret and deleting the old (no native rename)."""
        current = self.get_secret_map(old.folder, old.name)
        moved = SecretMap(
            backend=self.backend_id,
            folder=new.folder,
            name=new.name,
            values=current.values,
            description=current.description,
            tags=current.tags,
        )
        self.put_secret_map(moved)
        if (old.folder, old.name) != (new.folder, new.name):
            self.delete_secret_map(old.folder, old.name)

    def test_connection(self) -> BackendStatus:
        """Verify caller identity and ``ListSecrets`` access."""
        try:
            import boto3

            session = boto3.session.Session(profile_name=self.profile, region_name=self.region)
            identity = session.client("sts").get_caller_identity()
            self.client.list_secrets(MaxResults=1)
            detail = f"Account {identity.get('Account')} as {identity.get('Arn')}"
            return BackendStatus(self.backend_id, True, detail)
        except Exception as exc:
            return BackendStatus(self.backend_id, False, str(exc))

    def caller_identity(self) -> dict[str, str]:
        """Return the current STS caller identity (Account, Arn, UserId)."""
        import boto3

        session = boto3.session.Session(profile_name=self.profile, region_name=self.region)
        identity: dict[str, str] = session.client("sts").get_caller_identity()
        return identity

    def resolved_region(self) -> str | None:
        """Return the region this backend's session would actually use."""
        import boto3

        session = boto3.session.Session(profile_name=self.profile, region_name=self.region)
        region: str | None = session.region_name
        return region


def available_profiles() -> list[str]:
    """Return the AWS profile names configured locally (empty if boto3 absent)."""
    try:
        import boto3
    except ImportError:
        return []
    return list(boto3.session.Session().available_profiles)
