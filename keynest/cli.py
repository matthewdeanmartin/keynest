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


def _is_dry_run(args: argparse.Namespace) -> bool:
    """Return ``True`` if ``--dry-run`` was requested for this invocation."""
    return bool(getattr(args, "dry_run", False))


def _announce_dry_run(message: str) -> int:
    """Print a ``[dry-run]`` notice describing a skipped side effect; return 0."""
    print(f"[dry-run] {message}")
    return 0


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
    if not _is_dry_run(args):
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
    if _is_dry_run(args):
        return _announce_dry_run(f"would set {args.key} in {secret_map.path} ({len(secret_map.values)} key(s))")
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
    if _is_dry_run(args):
        keys = ", ".join(secret_map.keys) or "(none)"
        return _announce_dry_run(
            f"would run {' '.join(args.command)} with {len(secret_map.values)} injected var(s): {keys}"
        )
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
    if _is_dry_run(args):
        keys = ", ".join(sorted(result.values)) or "(none)"
        return _announce_dry_run(f"would import {len(result.values)} key(s) into {secret_map.path}: {keys}")
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
    if _is_dry_run(args):
        return _announce_dry_run(f"would write {len(secret_map.values)} key(s) to {args.file} (plaintext)")
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


def cmd_diff(args: argparse.Namespace) -> int:
    """Show the key-level diff between two secret maps."""
    from keynest.services import maptools  # pylint: disable=import-outside-toplevel

    backend = _get_backend(args)
    left = backend.get_secret_map(*parse_path(args.left))
    right = backend.get_secret_map(*parse_path(args.right))
    diff = maptools.diff_maps(left, right)
    print(f"{left.path} -> {right.path}")
    for key in diff.added:
        print(f"  + {key}")
    for key in diff.removed:
        print(f"  - {key}")
    for key in diff.changed:
        print(f"  ~ {key}")
    if not diff.has_changes:
        print("  (identical keys and values)")
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    """Lint a secret map's key names and value hygiene."""
    from keynest.services import maptools  # pylint: disable=import-outside-toplevel

    backend = _get_backend(args)
    secret_map = backend.get_secret_map(*parse_path(args.path))
    findings = maptools.lint_map(secret_map)
    if not findings:
        print(f"{secret_map.path}: clean")
        return 0
    for finding in findings:
        print(f"{secret_map.path}: {finding.key}: {finding.message}")
    return 1


def cmd_stale(args: argparse.Namespace) -> int:
    """List secret maps not updated within the staleness window."""
    from keynest.services import maptools  # pylint: disable=import-outside-toplevel
    from keynest.services.index_store import IndexStore  # pylint: disable=import-outside-toplevel

    index = IndexStore()
    stale_any = False
    for item in sorted(index.items(), key=lambda i: (i.folder, i.name)):
        if maptools.is_stale(item.updated_at, stale_days=args.days):
            stale_any = True
            age = maptools.age_in_days(item.updated_at)
            age_text = f"{age:.0f}d" if age is not None else "unknown"
            print(f"/{item.folder}/{item.name}  (age: {age_text}, updated: {item.updated_at or 'never'})")
    if not stale_any:
        print(f"No maps older than {args.days} days.")
    return 0


def cmd_redact_export(args: argparse.Namespace) -> int:
    """Print a redacted JSON view of a secret map (safe to share)."""
    from keynest.services import maptools  # pylint: disable=import-outside-toplevel

    backend = _get_backend(args)
    secret_map = backend.get_secret_map(*parse_path(args.path))
    print(maptools.export_redacted_json(secret_map))
    return 0


def cmd_duplicate(args: argparse.Namespace) -> int:
    """Duplicate a secret map under a new name (and optional folder)."""
    from keynest.services import maptools  # pylint: disable=import-outside-toplevel

    backend = _get_backend(args)
    source = backend.get_secret_map(*parse_path(args.path))
    copy = maptools.duplicate_map(source, args.new_name, new_folder=args.folder)
    if _is_dry_run(args):
        return _announce_dry_run(f"would duplicate {source.path} to {copy.path} ({len(copy.values)} key(s))")
    backend.put_secret_map(copy)
    print(f"Duplicated {source.path} to {copy.path}")
    return 0


def cmd_recent(args: argparse.Namespace) -> int:
    """Show recent (non-secret) usage events from the audit log."""
    events = AuditLog().events(limit=args.limit)
    if not events:
        print("(no audit events)")
        return 0
    for event in events:
        key = f" {event.key}" if event.key else ""
        print(f"{event.timestamp}  {event.action:<12} /{event.folder}/{event.name}{key}  [{event.backend}]")
    return 0


def cmd_diagnostics(args: argparse.Namespace) -> int:
    """Print environment and store diagnostics (keyring backend, paths, health)."""
    from keynest.services import diagnostics  # pylint: disable=import-outside-toplevel

    _ = args
    for line in diagnostics.collect().as_lines():
        print(line)
    return 0


def cmd_backup_index(args: argparse.Namespace) -> int:
    """Back up the non-secret local index to a timestamped file."""
    from keynest.services.index_store import IndexStore  # pylint: disable=import-outside-toplevel

    index = IndexStore()
    if _is_dry_run(args):
        return _announce_dry_run(f"would back up index at {index.path}")
    destination = index.backup()
    if destination is None:
        print("No index file to back up.")
        return 0
    print(f"Backed up index to {destination}")
    return 0


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
    common.add_argument(
        "--dry-run",
        action="store_true",
        help="Describe side effects without performing them (for smoke tests).",
    )

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

    p_diff = sub.add_parser("diff", parents=[common], help="Diff two secret maps (keys only).")
    p_diff.add_argument("left", help="Baseline folder/name path.")
    p_diff.add_argument("right", help="Comparison folder/name path.")
    p_diff.set_defaults(func=cmd_diff)

    p_lint = sub.add_parser("lint", parents=[common], help="Lint key names and value hygiene.")
    p_lint.add_argument("path", help="folder/name path.")
    p_lint.set_defaults(func=cmd_lint)

    p_stale = sub.add_parser("stale", parents=[common], help="List stale (old) secret maps.")
    p_stale.add_argument("--days", type=int, default=90, help="Staleness threshold in days (default 90).")
    p_stale.set_defaults(func=cmd_stale)

    p_red = sub.add_parser("redact-export", parents=[common], help="Print a redacted JSON view.")
    p_red.add_argument("path", help="folder/name path.")
    p_red.set_defaults(func=cmd_redact_export)

    p_dup = sub.add_parser("duplicate", parents=[common], help="Duplicate a secret map.")
    p_dup.add_argument("path", help="Source folder/name path.")
    p_dup.add_argument("new_name", help="Name for the duplicate.")
    p_dup.add_argument("--folder", help="Destination folder (default: same as source).")
    p_dup.set_defaults(func=cmd_duplicate)

    p_recent = sub.add_parser("recent", parents=[common], help="Show recent usage audit events.")
    p_recent.add_argument("--limit", type=int, default=20, help="Max events to show (default 20).")
    p_recent.set_defaults(func=cmd_recent)

    p_diag = sub.add_parser("diagnostics", parents=[common], help="Show environment diagnostics.")
    p_diag.set_defaults(func=cmd_diagnostics)

    p_backup = sub.add_parser("backup-index", parents=[common], help="Back up the local non-secret index.")
    p_backup.set_defaults(func=cmd_backup_index)

    return parser


def _normalize_run_argv(argv: Sequence[str]) -> list[str]:
    """Prepare argv for the ``run`` subcommand.

    Two adjustments are needed because ``run`` collects its command via
    ``argparse.REMAINDER``, which greedily swallows everything after the path:

    1. Move a ``--dry-run`` flag that appears after ``run`` to just before the
       path, so argparse parses it as the option (not part of the command).
    2. Drop the first literal ``--`` separator so the command list is clean.
    """
    args = list(argv)
    if "run" not in args:
        return args
    run_idx = args.index("run")
    # Pull --dry-run out of wherever it landed and reinsert right after "run".
    if "--dry-run" in args[run_idx + 1 :]:
        args.remove("--dry-run")
        args.insert(run_idx + 1, "--dry-run")
    if "--" in args:
        args.remove("--")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    """Run the keynest CLI and return a process exit code."""
    raw = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(_normalize_run_argv(raw))
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
