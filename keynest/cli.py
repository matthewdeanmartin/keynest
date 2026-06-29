"""Command-line entry point for keynest.

The CLI exists because Bash and automation need it. Per the product opinion,
``run`` is promoted harder than ``get`` (which is useful but dangerous).

Examples:
    keynest list
    keynest list --folder mastodon-mock
    keynest get mastodon-mock/dev DATABASE_URL
    keynest set mastodon-mock/dev DATABASE_URL "postgres://..."
    keynest run mastodon-mock/dev -- python app.py
    keynest print-code mastodon-mock/dev --language python
    keynest import-env mastodon-mock/dev .env
    keynest export-env mastodon-mock/dev .env --i-understand-this-is-less-safe
    keynest aws-policy --folder mastodon-mock
    keynest health
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from keynest.__about__ import __version__
from keynest.backends.base import BackendError, SecretBackend, SecretMapNotFound
from keynest.backends.registry import get_backend
from keynest.model import BackendId, SecretMap, key_warning, parse_path
from keynest.services import codegen
from keynest.services.audit import AuditEvent, AuditLog
from keynest.services.aws_policy import generate_policy_json
from keynest.services.dotenv_parser import parse_dotenv_file, serialize_dotenv
from keynest.services.runner import run_with_secrets


def _backend_id(args: argparse.Namespace) -> BackendId:
    """Resolve the requested backend id from common args."""
    return "aws-secrets-manager" if getattr(args, "aws", False) else "os-keyring"


def _get_backend(args: argparse.Namespace) -> SecretBackend:
    """Build a backend from parsed args."""
    return get_backend(
        _backend_id(args),
        profile=getattr(args, "profile", None),
        region=getattr(args, "region", None),
    )


# -- command implementations -------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    """List secret maps, optionally filtered by folder."""
    backend = _get_backend(args)
    refs = backend.list_secret_maps(args.folder)
    if not refs:
        print("(no secret maps)")
        return 0
    for ref in refs:
        print(ref.path)
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    """Print a single key's value (less safe than ``run``)."""
    folder, name = parse_path(args.path)
    backend = _get_backend(args)
    secret_map = backend.get_secret_map(folder, name)
    if args.key not in secret_map.values:
        print(f"Key not found: {args.key}", file=sys.stderr)
        return 2
    AuditLog().record(AuditEvent(action="get", backend=secret_map.backend, folder=folder, name=name, key=args.key))
    value = secret_map.values[args.key]
    print(value if value is not None else "")
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    """Set a single key in a secret map, creating the map if needed."""
    folder, name = parse_path(args.path)
    backend = _get_backend(args)
    try:
        secret_map = backend.get_secret_map(folder, name)
    except SecretMapNotFound:
        secret_map = SecretMap(backend=_backend_id(args), folder=folder, name=name)
    warning = key_warning(args.key)
    if warning:
        print(f"Warning: {warning}", file=sys.stderr)
    secret_map.values[args.key] = args.value
    backend.put_secret_map(secret_map)
    print(f"Set {args.key} in {secret_map.path}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Run a command with the secret map injected into its environment."""
    folder, name = parse_path(args.path)
    backend = _get_backend(args)
    secret_map = backend.get_secret_map(folder, name)
    if not args.command:
        print("No command given after '--'.", file=sys.stderr)
        return 2
    AuditLog().record(AuditEvent(action="run", backend=secret_map.backend, folder=folder, name=name))
    return run_with_secrets(secret_map, list(args.command))


def cmd_print_code(args: argparse.Namespace) -> int:
    """Print a generated code snippet for the secret map."""
    folder, name = parse_path(args.path)
    backend = _get_backend(args)
    secret_map = backend.get_secret_map(folder, name)
    snippets = codegen.all_snippets(secret_map)
    if args.language:
        wanted = args.language.lower()
        snippets = [s for s in snippets if s.language == wanted or wanted in s.title.lower()]
        if not snippets:
            print(f"No snippet for language: {args.language}", file=sys.stderr)
            return 2
    for snippet in snippets:
        print(f"# {snippet.title}")
        print(snippet.code)
        print()
    return 0


def cmd_import_env(args: argparse.Namespace) -> int:
    """Import a ``.env`` file into a secret map."""
    folder, name = parse_path(args.path)
    result = parse_dotenv_file(args.file)
    for warning in result.warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    backend = _get_backend(args)
    try:
        secret_map = backend.get_secret_map(folder, name)
    except SecretMapNotFound:
        secret_map = SecretMap(backend=_backend_id(args), folder=folder, name=name)
    secret_map.values.update(result.values)
    backend.put_secret_map(secret_map)
    print(f"Imported {len(result.values)} key(s) into {secret_map.path}")
    return 0


def cmd_export_env(args: argparse.Namespace) -> int:
    """Export a secret map to a ``.env`` file (requires the scary flag)."""
    if not args.i_understand_this_is_less_safe:
        print(
            "Refusing to export. Exporting writes plaintext secrets to disk.\n"
            "Prefer `keynest run` or generated SDK code. To proceed anyway, pass\n"
            "--i-understand-this-is-less-safe.",
            file=sys.stderr,
        )
        return 2
    folder, name = parse_path(args.path)
    backend = _get_backend(args)
    secret_map = backend.get_secret_map(folder, name)
    with open(args.file, "w", encoding="utf-8") as handle:
        handle.write(serialize_dotenv(secret_map.values))
    AuditLog().record(AuditEvent(action="export-env", backend=secret_map.backend, folder=folder, name=name))
    print(f"Wrote {len(secret_map.values)} key(s) to {args.file} (plaintext).")
    return 0


def cmd_aws_policy(args: argparse.Namespace) -> int:
    """Generate a least-privilege IAM policy for keynest-managed secrets."""
    region = args.region
    account = args.account_id
    if not account or not region:
        try:
            # Imported lazily so non-AWS commands never require boto3 credentials.
            from keynest.backends.aws_secrets_manager import (  # pylint: disable=import-outside-toplevel
                AwsSecretsManagerBackend,
            )

            backend = AwsSecretsManagerBackend(profile=args.profile, region=region)
            identity = backend.caller_identity()
            account = account or identity.get("Account")
            region = region or backend.region or "us-east-1"
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"Could not auto-detect AWS identity ({exc}).", file=sys.stderr)
            account = account or "<account-id>"
            region = region or "<region>"
    print(generate_policy_json(region, account, folder=args.folder, allow_delete=args.allow_delete))
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    """Check backend connectivity."""
    rc = 0
    # Probe the OS keyring always; probe AWS only when --aws is given (needs creds).
    backend_ids: list[BackendId] = ["aws-secrets-manager"] if args.aws else ["os-keyring"]
    for backend_id in backend_ids:
        backend = get_backend(backend_id, profile=args.profile, region=args.region)
        status = backend.test_connection()
        marker = "ok " if status.ok else "FAIL"
        print(f"[{marker}] {backend_id}: {status.detail}")
        if not status.ok:
            rc = 1
    return rc


def cmd_aws_setup(args: argparse.Namespace) -> int:
    """Run the AWS Secrets Manager setup wizard interactively."""
    # Imported lazily so non-AWS commands never require boto3.
    from keynest.services.aws_wizard import AwsSetupWizard  # pylint: disable=import-outside-toplevel

    wizard = AwsSetupWizard(profile=args.profile, region=args.region)
    if not args.yes:
        print(
            "This wizard will check your AWS identity, probe ListSecrets, and create\n"
            f"then schedule deletion of a throwaway secret at devsecrets/default/test.\n"
            f"Profile: {args.profile or '(default chain)'}  Region: {args.region or '(resolved)'}\n"
        )
        if input("Proceed? [y/N] ").strip().lower() not in {"y", "yes"}:
            print("Aborted.")
            return 1

    rc = 0
    for step in wizard.run_all(allow_delete_in_policy=args.allow_delete):
        marker = "ok  " if step.ok else "FAIL"
        print(f"[{marker}] {step.name}: {step.detail}")
        if step.name == "policy" and step.ok:
            print("\n--- Suggested IAM policy ---")
            print(step.data["policy"])
        if not step.ok:
            rc = 1
    return rc


# -- parser ------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the keynest CLI."""
    parser = argparse.ArgumentParser(
        prog="keynest",
        description=(
            "Developer secret workbench: a pure-Python keystore with GUI and "
            "CLI for OS keyring and AWS Secrets Manager"
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--aws", action="store_true", help="Use the AWS Secrets Manager backend.")
    common.add_argument("--profile", help="AWS profile name (AWS backend).")
    common.add_argument("--region", help="AWS region (AWS backend).")

    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", parents=[common], help="List secret maps.")
    p_list.add_argument("--folder", help="Filter by folder.")
    p_list.set_defaults(func=cmd_list)

    p_get = sub.add_parser("get", parents=[common], help="Print one key (less safe than run).")
    p_get.add_argument("path", help="folder/name path.")
    p_get.add_argument("key", help="Key name to read.")
    p_get.set_defaults(func=cmd_get)

    p_set = sub.add_parser("set", parents=[common], help="Set one key.")
    p_set.add_argument("path", help="folder/name path.")
    p_set.add_argument("key", help="Key name.")
    p_set.add_argument("value", help="Value to store.")
    p_set.set_defaults(func=cmd_set)

    p_run = sub.add_parser("run", parents=[common], help="Run a command with secrets injected.")
    p_run.add_argument("path", help="folder/name path.")
    p_run.add_argument("command", nargs=argparse.REMAINDER, help="-- command [args...]")
    p_run.set_defaults(func=cmd_run)

    p_code = sub.add_parser("print-code", parents=[common], help="Print generated code snippets.")
    p_code.add_argument("path", help="folder/name path.")
    p_code.add_argument("--language", help="Filter by language (python, bash, java, ...).")
    p_code.set_defaults(func=cmd_print_code)

    p_imp = sub.add_parser("import-env", parents=[common], help="Import a .env file.")
    p_imp.add_argument("path", help="folder/name path.")
    p_imp.add_argument("file", help="Path to the .env file.")
    p_imp.set_defaults(func=cmd_import_env)

    p_exp = sub.add_parser("export-env", parents=[common], help="Export to .env (less safe).")
    p_exp.add_argument("path", help="folder/name path.")
    p_exp.add_argument("file", help="Destination .env path.")
    p_exp.add_argument(
        "--i-understand-this-is-less-safe",
        action="store_true",
        help="Required acknowledgement to write plaintext secrets to disk.",
    )
    p_exp.set_defaults(func=cmd_export_env)

    p_pol = sub.add_parser("aws-policy", parents=[common], help="Generate an IAM policy.")
    p_pol.add_argument("--folder", help="Scope the policy to one folder.")
    p_pol.add_argument("--account-id", help="AWS account id (auto-detected if omitted).")
    p_pol.add_argument("--allow-delete", action="store_true", help="Include delete/restore actions.")
    p_pol.set_defaults(func=cmd_aws_policy)

    p_health = sub.add_parser("health", parents=[common], help="Check backend connectivity.")
    p_health.set_defaults(func=cmd_health)

    p_setup = sub.add_parser("aws-setup", parents=[common], help="Run the AWS setup wizard.")
    p_setup.add_argument("--yes", action="store_true", help="Skip the confirmation prompt.")
    p_setup.add_argument("--allow-delete", action="store_true", help="Include delete/restore actions in the policy.")
    p_setup.set_defaults(func=cmd_aws_setup)

    return parser


def _strip_run_separator(argv: Sequence[str]) -> list[str]:
    """Drop the literal ``--`` separator that precedes a ``run`` command.

    argparse's REMAINDER keeps the leading ``--``; strip the first one so the
    resulting command list is clean.
    """
    args = list(argv)
    if "run" in args and "--" in args:
        args.remove("--")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    """Run the keynest CLI and return a process exit code."""
    raw = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(_strip_run_separator(raw))
    try:
        return int(args.func(args))
    except SecretMapNotFound as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except BackendError as exc:
        print(f"Backend error: {exc}", file=sys.stderr)
        return 1
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
