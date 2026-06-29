"""Headless AWS Secrets Manager setup wizard.

Implements the steps from the spec (§10) as small, individually callable methods
so both the CLI and the Tkinter GUI can drive the same logic:

1. detect AWS CLI/profile availability
2. show current caller identity
3. select profile/region
4. test ``secretsmanager:ListSecrets``
5. create a test secret under ``devsecrets/default/test``
6. delete (schedule deletion of) the test secret
7. generate a least-privilege IAM policy

Each step returns a :class:`WizardStep` so a front-end can render success/failure
and any human-readable detail uniformly. The wizard never raises for expected AWS
failures; it captures them in the step result instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from keynest.backends.aws_secrets_manager import (
    AwsSecretsManagerBackend,
    available_profiles,
    secret_name,
)
from keynest.model import SecretMap
from keynest.services.aws_policy import generate_policy_json

# The throwaway secret the wizard round-trips to prove write/delete access.
TEST_FOLDER = "default"
TEST_NAME = "test"


@dataclass
class WizardStep:
    """The outcome of one wizard step."""

    name: str
    ok: bool
    detail: str = ""
    data: dict[str, str] = field(default_factory=dict)


class AwsSetupWizard:
    """Drives AWS setup against a (possibly injected) backend.

    Args:
        profile: AWS profile to use, or ``None`` for the default chain.
        region: AWS region, or ``None`` to resolve from the profile/env.
        backend: A pre-built backend (mainly for tests); created lazily otherwise.
    """

    def __init__(
        self,
        profile: str | None = None,
        region: str | None = None,
        backend: AwsSecretsManagerBackend | None = None,
    ) -> None:
        """Store the selected profile/region and optional backend."""
        self.profile = profile
        self.region = region
        self._backend = backend

    @property
    def backend(self) -> AwsSecretsManagerBackend:
        """Return (lazily creating) the AWS backend for the chosen profile/region."""
        if self._backend is None:
            self._backend = AwsSecretsManagerBackend(profile=self.profile, region=self.region)
        return self._backend

    # -- step 1: detect ------------------------------------------------------

    def detect(self) -> WizardStep:
        """Detect whether boto3 and any local AWS profiles are available."""
        try:
            import boto3  # noqa: F401  # pylint: disable=import-outside-toplevel,unused-import
        except ImportError:
            return WizardStep("detect", False, "boto3 is not installed.")
        profiles = available_profiles()
        if profiles:
            detail = f"Found {len(profiles)} profile(s): {', '.join(profiles)}"
        else:
            detail = "boto3 is available; no named profiles found (default chain will be used)."
        return WizardStep("detect", True, detail, {"profiles": ",".join(profiles)})

    # -- step 2: identity ----------------------------------------------------

    def whoami(self) -> WizardStep:
        """Show the current STS caller identity for the selected profile/region."""
        try:
            identity = self.backend.caller_identity()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return WizardStep("identity", False, str(exc))
        account = identity.get("Account", "?")
        arn = identity.get("Arn", "?")
        return WizardStep(
            "identity",
            True,
            f"Account {account} as {arn}",
            {"account": account, "arn": arn},
        )

    # -- step 4: list-secrets probe -----------------------------------------

    def probe_list_secrets(self) -> WizardStep:
        """Verify ``secretsmanager:ListSecrets`` permission."""
        try:
            self.backend.client.list_secrets(MaxResults=1)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return WizardStep("list_secrets", False, str(exc))
        return WizardStep("list_secrets", True, "ListSecrets permitted.")

    # -- step 5/6: test secret lifecycle ------------------------------------

    def create_test_secret(self) -> WizardStep:
        """Create the throwaway secret ``devsecrets/default/test``."""
        sid = secret_name(TEST_FOLDER, TEST_NAME)
        try:
            self.backend.put_secret_map(
                SecretMap(
                    backend="aws-secrets-manager",
                    folder=TEST_FOLDER,
                    name=TEST_NAME,
                    values={"KEYNEST_SETUP_PROBE": "ok"},
                    description="Temporary keynest setup probe; safe to delete.",
                )
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return WizardStep("create_test", False, str(exc), {"secret_id": sid})
        return WizardStep("create_test", True, f"Created {sid}.", {"secret_id": sid})

    def delete_test_secret(self) -> WizardStep:
        """Schedule deletion of the throwaway test secret."""
        sid = secret_name(TEST_FOLDER, TEST_NAME)
        try:
            self.backend.delete_secret_map(TEST_FOLDER, TEST_NAME)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return WizardStep("delete_test", False, str(exc), {"secret_id": sid})
        return WizardStep("delete_test", True, f"Scheduled deletion of {sid}.", {"secret_id": sid})

    # -- step 7: policy ------------------------------------------------------

    def generate_policy(self, *, allow_delete: bool = False) -> WizardStep:
        """Generate a least-privilege IAM policy for the resolved account/region."""
        try:
            identity = self.backend.caller_identity()
            account = identity["Account"]
            region = self.region or self.backend.resolved_region() or "us-east-1"
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return WizardStep("policy", False, str(exc))
        policy = generate_policy_json(region, account, allow_delete=allow_delete)
        return WizardStep("policy", True, "Generated IAM policy.", {"policy": policy})

    # -- orchestration -------------------------------------------------------

    def run_all(self, *, allow_delete_in_policy: bool = False) -> list[WizardStep]:
        """Run every step in order, stopping at the first hard failure.

        The test-secret cleanup (step 6) is always attempted if step 5 succeeded,
        even when an earlier policy generation would fail, so we never leave the
        probe secret behind.

        Args:
            allow_delete_in_policy: Include delete/restore actions in the policy.

        Returns:
            The ordered list of :class:`WizardStep` results produced.
        """
        steps: list[WizardStep] = []

        detect = self.detect()
        steps.append(detect)
        if not detect.ok:
            return steps

        identity = self.whoami()
        steps.append(identity)
        if not identity.ok:
            return steps

        probe = self.probe_list_secrets()
        steps.append(probe)
        if not probe.ok:
            return steps

        created = self.create_test_secret()
        steps.append(created)
        if created.ok:
            steps.append(self.delete_test_secret())

        steps.append(self.generate_policy(allow_delete=allow_delete_in_policy))
        return steps
