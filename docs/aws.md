# AWS Secrets Manager

AWS mode is opt-in per CLI command or through the GUI backend selector. boto3 uses its normal credential provider
chain: environment variables, shared AWS config/credentials, IAM Identity Center and process providers, or instance
and container roles. `--profile` selects a named profile and `--region` selects the region.

```console
keynest health --aws --profile personal --region us-east-1
keynest list --aws --profile personal --region us-east-1
keynest set my-app/dev API_TOKEN value --aws --profile personal --region us-east-1
```

Backend selection is not stored globally. Supply the AWS options on each CLI invocation. The GUI currently creates
its AWS backend without profile or region controls, so it relies on boto3's default chain and resolved region.

## Naming and discovery

Each map is one JSON `SecretString` named `devsecrets/folder/name`. keynest adds these tags:

- `ManagedBy=DeveloperSecretWorkbench`
- `OwnerMode=SingleDeveloper`
- `Folder=<folder>`
- `Name=<name>`
- `Schema=SecretMapV1`

Listing asks AWS for secrets carrying a `ManagedBy` tag, then verifies its exact value and name shape. It does not list
ordinary secrets as keynest maps. AWS permissions may still allow the identity to access other secrets; the generated
policy is intended to reduce that scope.

## Policy generation

Generate a starting policy with explicit identity details when possible:

```console
keynest aws-policy --account-id 123456789012 --region us-east-1
keynest aws-policy --folder my-app --account-id 123456789012 --region us-east-1
```

The policy grants management operations on `devsecrets/*` (or the selected folder) and a separate `ListSecrets`
permission, because AWS listing cannot be resource-scoped in the same way. Delete and restore permissions are omitted
unless `--allow-delete` is supplied. Review the output with your AWS administrator; generated policy is not proof that
the surrounding identity, KMS key, organization policies, or network are correctly configured.

## Setup wizard

```console
keynest aws-setup --profile personal --region us-east-1
```

After confirmation, the wizard:

1. verifies boto3 availability;
1. calls STS to identify the caller;
1. probes `ListSecrets`;
1. creates `devsecrets/default/test` with a throwaway payload;
1. schedules that test secret for deletion; and
1. prints a suggested policy.

If cleanup fails, inspect and remove or schedule deletion of the test secret yourself. AWS charges and CloudTrail
events can apply. The identity running the wizard needs delete permission for cleanup even though the policy printed
without `--allow-delete` intentionally omits ongoing delete/restore permission. `--yes` is non-interactive but still
performs the lifecycle. The currently accepted `--dry-run` option is not implemented by this wizard and must not be
used as a no-write guarantee.

## Operational limitations

- Values travel over the network to AWS and are protected according to AWS Secrets Manager and KMS configuration.
- Renaming is a create/update of the destination followed by scheduled deletion of the source; an existing destination
  can be overwritten.
- User description, tags from the editor, non-secret flags, and keynest timestamps are not round-tripped by the AWS
  backend. Only the fixed AWS tags and values are persisted.
- `stale` uses keynest's local index rather than AWS `LastChangedDate`.
- keynest does not rotate values, manage versions, restore scheduled secrets, or synchronize local and AWS maps.
