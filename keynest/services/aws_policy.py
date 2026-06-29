"""Generate a least-privilege IAM policy scoped to the ``devsecrets/*`` path."""

from __future__ import annotations

import json

# Actions always granted by the generated policy.
BASE_ACTIONS = [
    "secretsmanager:CreateSecret",
    "secretsmanager:PutSecretValue",
    "secretsmanager:GetSecretValue",
    "secretsmanager:DescribeSecret",
    "secretsmanager:TagResource",
]

# ListSecrets cannot be scoped to a resource ARN and must target "*".
LIST_ACTIONS = ["secretsmanager:ListSecrets"]

# Destructive actions, opt-in.
DELETE_ACTIONS = [
    "secretsmanager:DeleteSecret",
    "secretsmanager:RestoreSecret",
]


def secret_arn(region: str, account_id: str, path_glob: str = "devsecrets/*") -> str:
    """Return the Secrets Manager ARN pattern for the given path glob."""
    return f"arn:aws:secretsmanager:{region}:{account_id}:secret:{path_glob}"


def generate_policy(
    region: str,
    account_id: str,
    *,
    folder: str | None = None,
    allow_delete: bool = False,
) -> dict[str, object]:
    """Build an IAM policy document scoped to keynest-managed secrets.

    Args:
        region: AWS region, e.g. ``"us-east-1"``.
        account_id: 12-digit AWS account ID.
        folder: If given, scope the resource ARN to ``devsecrets/<folder>/*``.
        allow_delete: Include delete/restore actions when ``True``.

    Returns:
        An IAM policy document as a dict.
    """
    path_glob = f"devsecrets/{folder}/*" if folder else "devsecrets/*"
    resource = secret_arn(region, account_id, path_glob)

    actions = list(BASE_ACTIONS)
    if allow_delete:
        actions += DELETE_ACTIONS

    statements = [
        {
            "Sid": "KeynestManageSecrets",
            "Effect": "Allow",
            "Action": actions,
            "Resource": resource,
        },
        {
            "Sid": "KeynestListSecrets",
            "Effect": "Allow",
            "Action": LIST_ACTIONS,
            "Resource": "*",
        },
    ]
    return {"Version": "2012-10-17", "Statement": statements}


def generate_policy_json(
    region: str,
    account_id: str,
    *,
    folder: str | None = None,
    allow_delete: bool = False,
) -> str:
    """Return :func:`generate_policy` rendered as pretty JSON."""
    return json.dumps(
        generate_policy(region, account_id, folder=folder, allow_delete=allow_delete),
        indent=2,
    )
