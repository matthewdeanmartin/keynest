"""Tests for the AWS setup wizard service using a fake backend/client."""

from __future__ import annotations

import pytest

from keynest.backends.aws_secrets_manager import AwsSecretsManagerBackend, secret_name
from keynest.services.aws_wizard import TEST_FOLDER, TEST_NAME, AwsSetupWizard
from tests.test_aws_backend import FakeSecretsClient


class FakeBackend(AwsSecretsManagerBackend):
    """Real backend logic over a fake client, with a stubbed STS identity."""

    def __init__(self, identity="__default__", region="us-east-1"):
        super().__init__(client=FakeSecretsClient())
        # identity=None explicitly means "STS fails"; the sentinel means "use default".
        if identity == "__default__":
            identity = {"Account": "123456789012", "Arn": "arn:test"}
        self._identity = identity
        self._region = region

    def caller_identity(self):
        if self._identity is None:
            raise RuntimeError("no credentials")
        return self._identity

    def resolved_region(self):
        return self._region


def test_detect_finds_boto3():
    # boto3 is installed in the test environment, so detect should succeed.
    step = AwsSetupWizard().detect()
    assert step.ok


def test_whoami_reports_identity():
    wizard = AwsSetupWizard(backend=FakeBackend())
    step = wizard.whoami()
    assert step.ok
    assert step.data["account"] == "123456789012"


def test_whoami_failure_is_captured():
    wizard = AwsSetupWizard(backend=FakeBackend(identity=None))
    step = wizard.whoami()
    assert not step.ok
    assert "no credentials" in step.detail


def test_probe_list_secrets_ok():
    wizard = AwsSetupWizard(backend=FakeBackend())
    assert wizard.probe_list_secrets().ok


def test_test_secret_lifecycle_creates_then_deletes():
    backend = FakeBackend()
    wizard = AwsSetupWizard(backend=backend)
    sid = secret_name(TEST_FOLDER, TEST_NAME)

    created = wizard.create_test_secret()
    assert created.ok
    assert sid in backend.client.secrets

    deleted = wizard.delete_test_secret()
    assert deleted.ok
    assert sid not in backend.client.secrets


def test_generate_policy_uses_resolved_account_and_region():
    wizard = AwsSetupWizard(backend=FakeBackend(region="eu-west-1"))
    step = wizard.generate_policy()
    assert step.ok
    policy = step.data["policy"]
    assert "eu-west-1" in policy
    assert "123456789012" in policy
    assert "secretsmanager:DeleteSecret" not in policy


def test_generate_policy_allow_delete():
    wizard = AwsSetupWizard(backend=FakeBackend())
    step = wizard.generate_policy(allow_delete=True)
    assert "secretsmanager:DeleteSecret" in step.data["policy"]


def test_run_all_happy_path_cleans_up_and_generates_policy():
    backend = FakeBackend()
    wizard = AwsSetupWizard(backend=backend)
    steps = wizard.run_all()
    names = [s.name for s in steps]
    assert names == ["detect", "identity", "list_secrets", "create_test", "delete_test", "policy"]
    assert all(s.ok for s in steps)
    # The throwaway secret must not linger.
    assert secret_name(TEST_FOLDER, TEST_NAME) not in backend.client.secrets


def test_run_all_stops_at_identity_failure():
    wizard = AwsSetupWizard(backend=FakeBackend(identity=None))
    steps = wizard.run_all()
    assert [s.name for s in steps] == ["detect", "identity"]
    assert not steps[-1].ok


@pytest.mark.parametrize("allow_delete", [True, False])
def test_run_all_policy_delete_flag(allow_delete):
    wizard = AwsSetupWizard(backend=FakeBackend())
    steps = wizard.run_all(allow_delete_in_policy=allow_delete)
    policy = steps[-1].data["policy"]
    assert ("secretsmanager:DeleteSecret" in policy) is allow_delete
