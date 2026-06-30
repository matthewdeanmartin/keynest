# Security model and limitations

keynest is designed to reduce accidental plaintext files, commits, shell exports, and casual on-screen exposure. It
does not create a security boundary against code already running with your user or AWS identity.

## What keynest does

- Delegates local value protection to the OS credential store through Python `keyring`.
- Stores AWS values in Secrets Manager rather than a local index.
- Keeps local listing metadata separate from values.
- Masks values in the GUI, redacts reports by default, and auto-clears GUI clipboard copies after 30 seconds when the
  clipboard has not changed.
- Injects values only into the selected child environment for `run`, without creating a file.
- Requires an explicit acknowledgement before `.env` export.
- Records selected activity without recording values.

## What keynest does not protect against

- Malware, debuggers, memory inspection, injected Python code, or another process running with sufficient authority.
- A compromised unlocked desktop, OS account, AWS identity, dependency, child process, shell, terminal, or clipboard.
- A child process logging or transmitting environment variables.
- Terminal history and process inspection when a value is supplied to `keynest set` as an argument.
- Plaintext created with `get`, `export-env`, generated snippets, manual copy, backups made outside keynest, or the
  consumer application.
- Loss of the native credential store. The local index backup contains no values.

Windows Credential Manager may be able to protect stored credential blobs at rest for the signed-in user, but keynest
does not gain exclusive ownership of them. keynest itself avoids enumeration and exact-lookups only its own service;
that behavior should not be mistaken for an OS access-control guarantee. See [Concepts and storage](concepts.md#why-keynest-cannot-see-your-other-windows-credentials).

## Local files

By default, keynest writes `~/.devsecrets/index.json` and `~/.devsecrets/audit.log`. Neither is intended to contain
values, but both reveal potentially sensitive metadata: project names, key names, use times, and activity. Protect
them with normal user-account permissions and avoid committing the directory. `DEVSECRETS_HOME` changes the location.

The application does not currently enforce or repair restrictive permissions on these files. Index backup makes
another metadata copy beside the original.

## Safer operating habits

1. Prefer `keynest run` over `get`, shell export, or `.env` export.
1. Use the GUI rather than placing a new value in command history with `set`.
1. Run only trusted child commands and keep dependencies current.
1. Scope AWS permissions to the required `devsecrets` prefix and profile; review KMS and CloudTrail configuration.
1. Lock the desktop, use OS disk protection, and treat clipboard/history capture tools as part of the threat model.
1. Use a dedicated team secret manager when access sharing, revocation, approvals, rotation, or tamper-resistant audit
   is required.

For private vulnerability reporting and supported-version policy, see the repository's
[Security Policy](https://github.com/matthewdeanmartin/keynest/blob/main/SECURITY.md).
