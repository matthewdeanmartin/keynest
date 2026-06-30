# Command-line interface

The `keynest` command is intended for terminals, scripts, and child-process environment injection. The OS keyring is
the default backend. Add `--aws` to a command to address AWS Secrets Manager; `--profile` and `--region` select its
boto3 session.

```console
keynest --help
keynest COMMAND --help
keynest --version
```

Options common to subcommands are written after the command, for example:

```console
keynest list --aws --profile personal --region us-east-1
```

## Paths and exit status

Use `folder/name` or `/folder/name`; a bare `name` uses the `default` folder. Successful commands normally return 0.
A missing map or key and a refused unsafe export return 2. Backend or input errors generally return 1. `lint` returns
1 when it finds issues, and `run` returns the child process's exit code.

## Everyday commands

### `list`

List known map paths without reading their values:

```console
keynest list
keynest list --folder my-app
keynest list --aws --profile personal --region us-east-1
```

OS-keyring listing comes from the [non-secret index](../concepts.md#the-non-secret-local-index). AWS listing includes
only keynest-tagged secrets whose names match its convention.

### `set`

Set or replace one key, creating the map if necessary:

```console
keynest set my-app/dev DATABASE_URL "postgresql://..."
```

The value is a command-line argument and may be retained in shell history or visible to process-inspection tools.
For interactive secret entry, the GUI is usually a better choice. `set` stores strings; it does not parse JSON scalar
syntax.

### `run` (recommended)

Launch a command with every non-null map value merged into a copy of the current environment:

```console
keynest run my-app/dev -- python app.py
keynest run frontend/dev -- npm run dev
keynest run containers/local -- docker compose up
```

Map keys override existing variables in the child only. keynest does not invoke a shell: the words after `--` are the
executable and its argument vector. Shell syntax such as pipes, redirects, variable expansion, and shell built-ins
requires explicitly launching your shell. The child inherits the environment and can print, copy, or leak it, so run
only trusted commands. No plaintext file is created by keynest.

### `get`

Print one raw value to standard output:

```console
keynest get my-app/dev DATABASE_URL
```

This is deliberately less safe than `run`: terminals, scrollback, command substitution, logs, and downstream pipes
can expose the output. A null value prints as an empty line.

### `duplicate`

Copy a map's values and metadata under a new name, optionally in another folder:

```console
keynest duplicate my-app/dev dev-copy
keynest duplicate my-app/dev staging --folder another-app
```

This writes through the selected backend. It overwrites the destination if that map already exists.

## Import and export

### `import-env`

Merge a `.env` file into an existing or new map:

```console
keynest import-env my-app/dev .env
```

The parser accepts blank lines, comments, `KEY=value`, optional `export`, and single- or double-quoted values. It does
not interpolate `${OTHER}`. Imported keys replace matching keys and leave other existing keys untouched. Warnings are
printed for malformed lines, duplicates, non-portable keys, whitespace, and newlines. The source file remains on disk;
delete it separately if appropriate and verify it was never committed.

### `export-env`

Plaintext export is blocked unless you acknowledge the risk:

```console
keynest export-env my-app/dev .env --i-understand-this-is-less-safe
```

The destination is overwritten. File permissions are not specially hardened by keynest. Prefer `run` whenever the
consumer can accept environment variables.

### `redact-export`

Print shareable JSON with secret values replaced by `***REDACTED***`:

```console
keynest redact-export my-app/dev
```

Values explicitly marked as non-secret configuration are retained. The GUI can represent that distinction in the
model, but it currently offers no control to toggle it, and AWS does not persist the designation; therefore most
values will be redacted in normal use.

## Inspection and maintenance

### `diff`

Compare two maps in the same selected backend:

```console
keynest diff my-app/dev my-app/prod
```

Output identifies added (`+`), removed (`-`), and value-changed (`~`) keys without printing values. Values are read
and compared in memory.

### `lint`

Check key names plus leading/trailing whitespace and newline hazards:

```console
keynest lint my-app/dev
```

This is advisory and does not change the map. Findings produce exit status 1, making the command useful in scripts.

### `stale`

Report local-index entries whose update timestamp is old or missing:

```console
keynest stale
keynest stale --days 30
```

This command reads only the local non-secret index. It does not query AWS ages, even if AWS-related common options are
supplied, and it does not rotate anything.

### `recent`

Display the last local non-secret audit events (20 by default):

```console
keynest recent
keynest recent --limit 50
```

### `diagnostics`

Show Python and platform information, the active keyring implementation, index and audit paths, and keyring-specific
notes without reading secret values:

```console
keynest diagnostics
```

### `health`

Exercise a temporary write/read/delete round trip against the OS keyring, or check STS identity and `ListSecrets`
access in AWS mode:

```console
keynest health
keynest health --aws --profile personal --region us-east-1
```

The OS check temporarily writes a credential under keynest's service. AWS health does not create a secret.

### `backup-index`

Copy `index.json` to a timestamped `.json.bak` sibling:

```console
keynest backup-index
```

This backs up names and metadata only. It does not back up secret values or the audit log.

## Code generation

Print usage templates for the selected map:

```console
keynest print-code my-app/dev
keynest print-code my-app/dev --language python
keynest print-code my-app/dev --language java
```

Templates cover `keynest run`, raw Python keyring, Python boto3, direct shell lookup, Node/TypeScript AWS SDK, Java AWS
SDK, Docker, Docker Compose, and a manual copy checklist. They are starting points: inspect dependencies, names,
regions, and error handling before using them. The command emits examples for both backends for reference, not only
examples appropriate to the selected map.

## AWS commands

`aws-policy` prints a policy scoped to `devsecrets/*` or one folder. It tries to discover the account and region when
they are omitted and prints placeholders if discovery fails:

```console
keynest aws-policy --account-id 123456789012 --region us-east-1
keynest aws-policy --folder my-app --allow-delete --profile personal --region us-east-1
```

`aws-setup` checks boto3, resolves the caller, tests listing, creates a throwaway
`devsecrets/default/test`, schedules its deletion, and prints a suggested policy:

```console
keynest aws-setup --profile personal --region us-east-1
keynest aws-setup --yes --allow-delete
```

`--yes` skips only the prompt; it does not skip the AWS writes. `--allow-delete` adds delete/restore permissions to the
generated policy. See the [AWS guide](../aws.md) before running the wizard.

## Dry runs

`--dry-run` is useful on the mutating `set`, `run`, `import-env`, `export-env`, `duplicate`, and `backup-index`
commands. It describes the skipped action; for `get`, it suppresses the audit event but still prints the requested
value. Read-only commands may accept the common flag without changing their behavior. In particular, do not assume
that `aws-setup --dry-run` is safe: the setup wizard currently ignores that flag and performs its documented test
secret lifecycle after confirmation.
