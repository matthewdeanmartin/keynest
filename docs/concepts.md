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
slash (`my-app/dev`). A bare name such as `github-token` means `/default/github-token`.

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

### Why keynest cannot see your other Windows credentials

keynest does not scan Windows Credential Manager. It asks `keyring` for an exact service and username, always using
the service `DeveloperSecretWorkbench` and a map path that keynest already knows. The `keyring` backend interface used
by keynest has exact get/set/delete operations but no portable list-all operation.

Windows does have a native `CredEnumerate` API, so saying that Windows has *no* enumeration power would be inaccurate.
keynest does not call that API, and the Windows implementation in Python `keyring` does not use it for keynest's list
operation. Consequently, credentials created by browsers, Git, other applications, or another `keyring` service do
not appear in keynest. This is an implementation boundary, not a security sandbox: another process running with your
user's authority may be able to inspect credentials your user can access.

The same practical rule applies on macOS and Linux: keynest addresses its own known entries and does not import or
inventory unrelated entries from the native store.

### The non-secret local index

Native keyring APIs do not provide keynest with one portable way to list its maps. keynest therefore maintains:

```text
~/.devsecrets/index.json
```

Set `DEVSECRETS_HOME` to relocate the `.devsecrets` data directory. The index contains map names, folders, key names,
descriptions, tags, non-secret designations, and timestamps, but never values.

The OS credential store is the source of truth for values; the index is the source for listing and local metadata.
If the index is deleted, the credentials are not automatically deleted, but keynest no longer knows which paths to
list. There is currently no automatic index reconstruction or credential discovery. Saving a map again at the exact
path re-creates its index entry but overwrites that map's stored payload.

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
| Listing | Local non-secret index | AWS list filtered by tag and name |
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
