# Concepts and storage

## Secret maps

The unit of storage is a **secret map**: a flat JSON-compatible dictionary. A map might contain all configuration for
one application and environment:

```json
{
  "DATABASE_URL": "postgresql://...",
  "OPENAI_API_KEY": "...",
  "LOG_LEVEL": "info"
}
```

Values may be strings, numbers, booleans, or null. Environment injection converts non-string scalars to strings and
skips null values. Nested objects and arrays are not part of the model.

Keys should use portable environment-variable syntax: letters, digits, and underscores, without a leading digit.
keynest warns about incompatible names but does not always reject them. A map also has a backend, folder, name,
description, tags, timestamps, and a list of values designated as non-secret configuration. Some metadata support is
currently backend-specific; see [Backend differences](#backend-differences).

## Paths and folders

The canonical path is `/folder/name`, for example `/my-app/dev`. CLI arguments accept that form without the leading
slash (`my-app/dev`). Outside a Git repository, a bare name such as `github-token` means
`/default/github-token`. Inside a repository it defaults to that repository's folder. Explicit paths always win; see
[repository-aware defaults](repositories.md).

Folders are organizational labels, not directories. The `default` folder always appears. Empty folders are not
persisted: a folder exists once it contains a map.

## OS keyring backend

This is the default backend. keynest calls the Python `keyring` package, which selects the native store available for
the current desktop session (normally Windows Credential Manager, macOS Keychain, Secret Service, or KWallet).

Each complete map is serialized as one JSON credential:

```text
service:  DeveloperSecretWorkbench
username: /folder/name
password: {"KEY":"value", ...}
```

The native `keyring` backend may translate those fields into platform-specific target names. Treat the representation
above as keynest's logical addressing scheme, not as a guarantee about labels displayed by every OS utility.

### Credential discovery

Python `keyring` exposes exact get/set/delete operations but no portable list operation. keynest adds enumeration for
the native Windows Credential Manager, macOS Keychain, Linux Secret Service, and Linux libsecret backends. keynest
keeps and returns only service and username identifiers; it does not display or persist values discovered during
enumeration.

The macOS and Linux implementations request attributes without requesting secret data. Windows' `CredEnumerate` API
returns native credential structures that may include credential blobs; keynest ignores those fields immediately and
retains only `TargetName` and `UserName`. The stronger claim that Windows enumeration never places a value in keynest's
process memory would therefore be inaccurate.

When enumeration succeeds, the native store is authoritative for which keynest maps exist. keynest filters entries
to the `DeveloperSecretWorkbench` service and parses their usernames as map paths. In the GUI, the optional
**Show all OS credentials (names only)** view also displays identifiers belonging to other services. Those entries
are read-only: keynest does not retrieve, reveal, import, edit, or delete their values. It can generate example code
that performs an explicit lookup if the user chooses to do that separately.

Enumeration is backend-specific, not guaranteed merely because the platform is supported. KWallet and unknown or
headless keyring implementations currently fall back to the local index and cannot populate the GUI's other-
credentials view. An enumeration error also degrades to the index.

Identifier-only discovery reduces unnecessary secret reads, but it is not a security sandbox. Credential names can
be sensitive metadata, and another process running with your user's authority may be able to retrieve values the OS
allows that user to access.

### The non-secret local index

Native keyring APIs do not provide one portable way to list maps, and even enumerable stores do not hold keynest's
extra metadata. keynest therefore maintains:

```text
~/.devsecrets/index.json
```

Set `DEVSECRETS_HOME` to relocate the `.devsecrets` data directory. The index contains map names, folders, key names,
descriptions, tags, non-secret designations, and timestamps, but never values.

The OS credential store is always the source of truth for values. On enumerable backends it is also the source of
truth for map existence; the index supplies descriptions, tags, key names, non-secret flags, and timestamps. On
non-enumerable backends, the index is additionally the listing source.

If the index is deleted, credentials remain in the OS store. Supported enumerable backends can still rediscover map
paths, but lost descriptions, tags, non-secret flags, and timestamps are not reconstructed. Non-enumerable backends
cannot list the orphaned entries. Saving a rediscovered map creates fresh index metadata.

`keynest backup-index` copies this metadata file beside the original with a UTC timestamp. It is not a secret backup
and cannot restore values.

## AWS Secrets Manager backend

AWS mode stores each map as one secret named:

```text
devsecrets/{folder}/{name}
```

The secret value is the map's JSON object. keynest marks its AWS secrets with `ManagedBy=DeveloperSecretWorkbench`
and other schema and path tags. Listing filters by the managed tag and then accepts only three-part
`devsecrets/folder/name` paths, so unrelated AWS secrets remain outside keynest's list.

AWS deletion uses a seven-day recovery window. A rename creates or overwrites the destination and then schedules the
source for deletion; it is not an atomic AWS rename. See [AWS Secrets Manager](aws.md) for credentials and policy
setup.

## Backend differences

| Capability | OS keyring | AWS Secrets Manager |
| --- | --- | --- |
| Values | Native credential entry containing JSON | AWS `SecretString` containing JSON |
| Listing | Native enumeration when supported; otherwise local index | AWS list filtered by tag and name |
| Description, user tags, non-secret flags | Stored in local index | Not currently persisted |
| Created/updated timestamps used by keynest | Local index | Not loaded into the map |
| Delete | Immediate keyring delete | Scheduled with seven-day recovery |
| Rename | Write destination, delete source | Write destination, schedule source deletion |
| Billing/network | Local OS facility | AWS permissions, network, and AWS charges apply |

The `stale` report reads the local index, so today it reports locally indexed OS-keyring maps, not AWS secret ages.

## Audit log

Selected CLI actions append JSON Lines to `~/.devsecrets/audit.log` (or the `DEVSECRETS_HOME` location). Events include
the action, backend, map path, timestamp, and sometimes a key name. Values are never recorded. CLI `get`, `run`, and
`export-env` record events. GUI copies and most management operations are not recorded. This is a local activity
history, not a tamper-resistant or complete security audit.
