"""Tests for the AWS backend using a fake Secrets Manager client.

These avoid any network/boto3 dependency by injecting a stub client that mimics
the small slice of the Secrets Manager API the backend uses.
"""

from __future__ import annotations

import json

import pytest

from keynest.backends.aws_secrets_manager import AwsSecretsManagerBackend, secret_name
from keynest.backends.base import SecretMapExists, SecretMapNotFound
from keynest.model import SecretMap, SecretMapRef


class _ResourceNotFound(Exception):
    pass


class _ResourceExists(Exception):
    pass


class FakeSecretsClient:
    """A minimal in-memory stand-in for a boto3 Secrets Manager client."""

    def __init__(self) -> None:
        self.secrets: dict[str, dict] = {}

        class _Exc:
            ResourceNotFoundException = _ResourceNotFound
            ResourceExistsException = _ResourceExists

        self.exceptions = _Exc()

    def create_secret(self, Name, SecretString, Tags):
        if Name in self.secrets:
            raise _ResourceExists(Name)
        self.secrets[Name] = {"SecretString": SecretString, "Tags": Tags}

    def put_secret_value(self, SecretId, SecretString):
        self.secrets[SecretId]["SecretString"] = SecretString

    def tag_resource(self, SecretId, Tags):
        self.secrets[SecretId]["Tags"] = Tags

    def get_secret_value(self, SecretId):
        if SecretId not in self.secrets:
            raise _ResourceNotFound(SecretId)
        return {"SecretString": self.secrets[SecretId]["SecretString"]}

    def delete_secret(self, SecretId, RecoveryWindowInDays):
        if SecretId not in self.secrets:
            raise _ResourceNotFound(SecretId)
        del self.secrets[SecretId]

    def list_secrets(self, MaxResults=10):
        return {"SecretList": [{"Name": name} for name in list(self.secrets)[:MaxResults]]}

    def get_paginator(self, _name):
        client = self

        class _Paginator:
            def paginate(self, Filters):
                secret_list = [{"Name": name, "Tags": data["Tags"]} for name, data in client.secrets.items()]
                return [{"SecretList": secret_list}]

        return _Paginator()


@pytest.fixture
def backend() -> AwsSecretsManagerBackend:
    return AwsSecretsManagerBackend(client=FakeSecretsClient())


def _map(folder="my-app", name="dev", **values) -> SecretMap:
    return SecretMap(backend="aws-secrets-manager", folder=folder, name=name, values=values or {"K": "v"})


def test_secret_name_convention():
    assert secret_name("my-app", "dev") == "devsecrets/my-app/dev"


def test_put_get_roundtrip(backend):
    backend.put_secret_map(_map(DATABASE_URL="postgres://x"))
    loaded = backend.get_secret_map("my-app", "dev")
    assert loaded.values == {"DATABASE_URL": "postgres://x"}
    stored = backend.client.secrets["devsecrets/my-app/dev"]
    tags = {t["Key"]: t["Value"] for t in stored["Tags"]}
    assert tags["ManagedBy"] == "DeveloperSecretWorkbench"
    assert tags["Schema"] == "SecretMapV1"


def test_put_overwrites_existing(backend):
    backend.put_secret_map(_map(A="1"))
    backend.put_secret_map(_map(A="2"))
    assert backend.get_secret_map("my-app", "dev").values == {"A": "2"}


def test_create_conflict(backend):
    backend.create_secret_map(_map())
    with pytest.raises(SecretMapExists):
        backend.create_secret_map(_map())


def test_list_filters_by_managed_tag_and_folder(backend):
    backend.put_secret_map(_map(folder="a", name="one"))
    backend.put_secret_map(_map(folder="b", name="two"))
    # An unmanaged secret should be ignored by listing.
    backend.client.secrets["other/thing"] = {"SecretString": "{}", "Tags": []}
    assert backend.list_secret_maps() == [
        SecretMapRef("aws-secrets-manager", "a", "one"),
        SecretMapRef("aws-secrets-manager", "b", "two"),
    ]
    assert backend.list_secret_maps("a") == [SecretMapRef("aws-secrets-manager", "a", "one")]


def test_get_missing_raises(backend):
    with pytest.raises(SecretMapNotFound):
        backend.get_secret_map("nope", "nope")


def test_delete(backend):
    backend.put_secret_map(_map())
    backend.delete_secret_map("my-app", "dev")
    with pytest.raises(SecretMapNotFound):
        backend.get_secret_map("my-app", "dev")


def test_rename(backend):
    backend.put_secret_map(_map(folder="a", name="one", S="x"))
    backend.rename_secret_map(
        SecretMapRef("aws-secrets-manager", "a", "one"),
        SecretMapRef("aws-secrets-manager", "b", "two"),
    )
    assert backend.get_secret_map("b", "two").values == {"S": "x"}
    with pytest.raises(SecretMapNotFound):
        backend.get_secret_map("a", "one")


def test_stored_payload_is_json(backend):
    backend.put_secret_map(_map(A="1", B="2"))
    raw = backend.client.secrets["devsecrets/my-app/dev"]["SecretString"]
    assert json.loads(raw) == {"A": "1", "B": "2"}
