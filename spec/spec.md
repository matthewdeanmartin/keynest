# Spec: Developer Secret Workbench

Name: keynest

## 1. Product goal

A small Tkinter desktop app plus CLI that helps a single software developer stop storing secrets in Notepad, random `.env` files, shell history, and repo-adjacent config files.

The app manages secret maps in either:

1. the laptop OS secret store via Python `keyring`, or
1. AWS Secrets Manager via `boto3`.

The app’s primary UX goal is not merely “store and copy secrets.” It should make **safe usage paths easier than unsafe usage paths**.

Bad default:

```bash
export DATABASE_PASSWORD=...
```

Better default:

```bash
devsecrets run --folder my-app -- python app.py
```

Best developer experience:

```python
from devsecrets_sdk import get_secret_map

secrets = get_secret_map("my-app")
db_password = secrets["DATABASE_PASSWORD"]
```

## 2. Non-goals

V1 is **not**:

- a team secret manager
- a password manager replacement
- a browser autofill tool
- a SaaS
- a GitHub Actions secret sync tool
- a Kubernetes/Vault/Doppler replacement
- an enterprise approval/workflow/audit platform

Those can be future adapters.

## 3. Core model

All secrets are **secret maps**.

A secret map is a dictionary of string keys to secret-ish values:

```json
{
  "DATABASE_HOST": "localhost",
  "DATABASE_USER": "postgres",
  "DATABASE_PASSWORD": "secret",
  "DATABASE_NAME": "appdb",
  "OPENAI_API_KEY": "secret"
}
```

Values are usually strings, but the model should tolerate JSON-compatible scalar values for future use.

### Secret map identity

Each secret map has:

```text
backend: os-keyring | aws-secrets-manager
folder: string
name: string
version: optional string/backend-managed
```

Canonical logical path:

```text
/folder/name
```

Examples:

```text
/default/github
/default/aws-personal
/mastodon-mock/dev
/keepachangelog-manager/local
/client-x/staging
```

### Default folder

The app must always have a default folder named:

```text
/default
```

Creating a secret should not require choosing a folder. If the user does nothing, the secret goes into `/default`.

## 4. Backend design

### Backend interface

Implement a small internal interface:

```python
class SecretBackend(Protocol):
    def list_folders(self) -> list[str]: ...
    def list_secret_maps(self, folder: str) -> list[SecretMapRef]: ...
    def get_secret_map(self, folder: str, name: str) -> SecretMap: ...
    def put_secret_map(self, secret_map: SecretMap) -> None: ...
    def delete_secret_map(self, folder: str, name: str) -> None: ...
    def rename_secret_map(self, old: SecretMapRef, new: SecretMapRef) -> None: ...
    def test_connection(self) -> BackendStatus: ...
```

### OS keyring backend

Use Python package:

```text
keyring
```

Problem: `keyring` stores individual username/password-ish entries, not rich folders and maps.

Recommended storage strategy:

```text
service_name = "DeveloperSecretWorkbench"
username = f"{folder}/{name}"
password = JSON string of the secret map payload
```

Example:

```python
keyring.set_password(
    "DeveloperSecretWorkbench",
    "/mastodon-mock/dev",
    json.dumps({
        "DATABASE_URL": "...",
        "MASTODON_TOKEN": "..."
    }),
)
```

Metadata is the annoying part. Since OS keyrings are not ideal for listing arbitrary entries, keep a non-secret local index file:

```text
~/.devsecrets/index.json
```

The index may contain names, folders, backend IDs, timestamps, key names, descriptions, and tags, but **never secret values**.

Example:

```json
{
  "version": 1,
  "items": [
    {
      "backend": "os-keyring",
      "folder": "/mastodon-mock",
      "name": "dev",
      "keys": ["DATABASE_URL", "MASTODON_TOKEN"],
      "created_at": "2026-06-29T12:00:00-04:00",
      "updated_at": "2026-06-29T12:05:00-04:00"
    }
  ]
}
```

### AWS Secrets Manager backend

Store each secret map as one AWS Secrets Manager secret with a JSON `SecretString`.

Suggested naming convention:

```text
devsecrets/{folder}/{name}
```

Examples:

```text
devsecrets/default/github
devsecrets/mastodon-mock/dev
devsecrets/client-x/staging
```

Folder `/default` maps to:

```text
devsecrets/default/<name>
```

AWS metadata tags:

```text
ManagedBy = DeveloperSecretWorkbench
OwnerMode = SingleDeveloper
Folder = mastodon-mock
Name = dev
Schema = SecretMapV1
```

The GUI should generate an IAM policy that locks access down to the current AWS identity and the `devsecrets/*` path.

## 5. GUI layout

Tkinter app with a practical three-panel layout.

```text
┌───────────────────────────────────────────────────────────────┐
│ Menu: File Backend Tools Code Help                            │
├───────────────┬───────────────────────────────┬───────────────┤
│ Folders       │ Secret Maps                   │ Actions       │
│               │                               │               │
│ /default      │ Name: github                  │ Use Secret    │
│ /my-app       │ Backend: OS keyring           │ Copy          │
│ /client-x     │ Keys: 4                       │ Generate Code │
│               │                               │ Run Command   │
│               │ Key table                     │ AWS Policy    │
│               │ ┌───────────────────────────┐ │ Import        │
│               │ │ KEY             VALUE     │ │ Export        │
│               │ │ DATABASE_URL    •••••••   │ │ Health Check  │
│               │ │ API_TOKEN       •••••••   │ │               │
│               │ └───────────────────────────┘ │               │
└───────────────┴───────────────────────────────┴───────────────┘
```

### Left panel: folders

Features:

- default folder always present

- create folder

- rename folder

- delete empty folder

- show counts

- backend filter:

  - All
  - OS keyring
  - AWS Secrets Manager

### Middle panel: selected secret map

Fields:

- folder
- name
- backend
- description
- tags
- key/value grid

Key/value grid behavior:

- values masked by default

- per-cell reveal button

- per-row copy button

- add key

- rename key

- delete key

- duplicate key

- generate random value

- mark key as “non-secret config” vs “secret”

- validation for Bash-compatible names:

  - `DATABASE_URL` good
  - `database-url` warning
  - `1TOKEN` warning

### Right panel: usage actions

This is where the app becomes useful.

Actions:

- Run command with secrets
- Generate code snippet
- Generate CLI command
- Generate wrapper script
- Copy selected value
- Copy key name
- Copy secret reference
- Generate AWS IAM policy
- Generate `.gitignore` suggestions
- Scan selected folder for `.env` files
- Import from `.env`
- Dangerous export to `.env`

## 6. CLI

The CLI is not optional because Bash and automation need it.

Suggested commands:

```bash
devsecrets list
devsecrets list --folder mastodon-mock
devsecrets get mastodon-mock/dev DATABASE_URL
devsecrets set mastodon-mock/dev DATABASE_URL "postgres://..."
devsecrets edit mastodon-mock/dev
devsecrets run mastodon-mock/dev -- npm run dev
devsecrets run mastodon-mock/dev -- python app.py
devsecrets print-code mastodon-mock/dev --language python
devsecrets import-env mastodon-mock/dev .env
devsecrets export-env mastodon-mock/dev .env --i-understand-this-is-less-safe
devsecrets aws-policy --folder mastodon-mock
devsecrets health
```

Important: `get` is useful but dangerous. `run` should be promoted harder than `get`.

## 7. Safe usage workflows

### Workflow A: run a command with injected environment

```bash
devsecrets run mastodon-mock/dev -- python app.py
```

Behavior:

1. Load secret map from OS keyring or AWS.
1. Merge secrets into subprocess environment.
1. Start process.
1. Do not write secrets to disk.
1. Do not print secrets.
1. On exit, drop references.

This mirrors the best prior-art pattern from tools like 1Password, Doppler, Bitwarden, and Infisical.

### Workflow B: generate Python code

Generated Python snippet:

```python
from devsecrets_sdk import get_secret_map

secrets = get_secret_map("mastodon-mock/dev")
database_url = secrets["DATABASE_URL"]
```

AWS-specific version:

```python
import json
import boto3

client = boto3.client("secretsmanager")
response = client.get_secret_value(SecretId="devsecrets/mastodon-mock/dev")
secrets = json.loads(response["SecretString"])

database_url = secrets["DATABASE_URL"]
```

OS-keyring-specific version:

```python
import json
import keyring

payload = keyring.get_password(
    "DeveloperSecretWorkbench",
    "/mastodon-mock/dev",
)
if payload is None:
    raise RuntimeError("Secret map not found: /mastodon-mock/dev")

secrets = json.loads(payload)
database_url = secrets["DATABASE_URL"]
```

### Workflow C: generate Node/TypeScript code

AWS SDK example:

```ts
import { SecretsManagerClient, GetSecretValueCommand } from "@aws-sdk/client-secrets-manager";

const client = new SecretsManagerClient({});
const response = await client.send(
  new GetSecretValueCommand({ SecretId: "devsecrets/mastodon-mock/dev" })
);

if (!response.SecretString) {
  throw new Error("SecretString was empty");
}

const secrets = JSON.parse(response.SecretString);
const databaseUrl = secrets.DATABASE_URL;
```

For local OS keyring, Node is trickier because Python `keyring` is not directly available. Recommended v1 path:

```bash
devsecrets run mastodon-mock/dev -- npm run dev
```

That avoids requiring a Node native keychain dependency.

### Workflow D: generate Java code

For AWS:

```java
SecretsManagerClient client = SecretsManagerClient.create();

GetSecretValueResponse response = client.getSecretValue(
    GetSecretValueRequest.builder()
        .secretId("devsecrets/mastodon-mock/dev")
        .build()
);

String json = response.secretString();
```

For local dev, prefer:

```bash
devsecrets run mastodon-mock/dev -- ./gradlew bootRun
```

### Workflow E: Bash

Preferred:

```bash
devsecrets run mastodon-mock/dev -- ./scripts/run-local.sh
```

Escape hatch:

```bash
DATABASE_URL="$(devsecrets get mastodon-mock/dev DATABASE_URL)"
```

The GUI should label this as “less safe: secret may enter shell history, process args, terminal scrollback, or logs depending on usage.”

## 8. `.env` policy

The app should support `.env` import because migration matters.

It should make `.env` export possible but socially awkward.

### Import `.env`

```bash
devsecrets import-env mastodon-mock/dev .env
```

GUI import behavior:

- parse file
- preview keys
- warn about suspicious values
- store into selected backend
- offer to add `.env` to `.gitignore`
- offer to rename original file to `.env.migrated.bak`
- offer to securely delete? Maybe no, because cross-platform secure deletion is hard to promise.

### Export `.env`

Export should require explicit friction:

```bash
devsecrets export-env mastodon-mock/dev .env --i-understand-this-is-less-safe
```

GUI wording:

> Exporting writes plaintext secrets to disk. Prefer “Run command with secrets” or generated SDK code.

Buttons:

- Recommended: Run command instead
- Recommended: Generate code instead
- Dangerous: Export `.env`

## 9. Copy/paste support

Copy/paste is allowed because tools like pgAdmin, database clients, SaaS dashboards, and one-off admin consoles sometimes require it.

Copy behavior:

- copy selected secret to clipboard

- show countdown

- auto-clear clipboard after configurable interval

- default: 30 seconds

- optional: clear on app minimize/close

- maintain local audit event:

  - copied key name
  - time
  - backend
  - never the value

Clipboard warning:

> Clipboard is shared OS state. Other apps may be able to read it. Prefer generated code or `devsecrets run` when possible.

## 10. AWS features

AWS must be first-class from day one.

### AWS setup wizard

The wizard should:

1. detect AWS CLI/profile availability
1. show current caller identity
1. select profile/region
1. test `secretsmanager:ListSecrets`
1. create a test secret under `devsecrets/default/test`
1. delete test secret or schedule deletion
1. generate least-privilege IAM policy

### AWS IAM policy generator

Generate a policy scoped to:

```text
arn:aws:secretsmanager:<region>:<account-id>:secret:devsecrets/*
```

Include actions:

```json
[
  "secretsmanager:CreateSecret",
  "secretsmanager:PutSecretValue",
  "secretsmanager:GetSecretValue",
  "secretsmanager:DescribeSecret",
  "secretsmanager:ListSecrets",
  "secretsmanager:TagResource",
  "secretsmanager:DeleteSecret",
  "secretsmanager:RestoreSecret"
]
```

Potentially omit delete by default and make it a checkbox.

### AWS local profile assumptions

V1 assumes:

- user already has AWS credentials configured
- user has permission to create/manage secrets
- user is storing developer secrets for themselves
- user is not building a multi-user governance platform

## 11. Search and discovery

Search fields:

- secret map name
- folder
- key names
- tags
- descriptions
- backend
- AWS ARN
- updated date

Never search secret values by default.

Optional advanced mode:

- “Search secret values locally”
- requires warning
- does not persist search index

## 12. Secret value tools

Per key:

- generate random password
- generate API token placeholder
- generate UUID
- generate hex token
- generate base64 token
- mark as rotated
- copy value
- reveal temporarily
- validate URL
- validate JSON
- validate PEM-ish text
- detect accidental whitespace/newline

For maps:

- compare two maps
- duplicate map
- move between backends
- sync OS keyring → AWS
- sync AWS → OS keyring
- rename folder/name
- import `.env`
- import JSON
- export redacted JSON
- export `.env` only with warning

## 13. Code generator

The GUI should have a “Use this secret” tab that generates:

- Bash `devsecrets run`
- Bash direct lookup
- Python with `devsecrets_sdk`
- Python raw `keyring`
- Python raw `boto3`
- Node/TypeScript AWS SDK
- Node/TypeScript via `devsecrets run`
- Java AWS SDK
- Java via `devsecrets run`
- Docker command
- Docker Compose snippet using runtime wrapper
- pgAdmin/manual copy checklist

The core value is here. This is the wedge.

## 14. Minimal dependency set

Required:

```text
Python 3.11+
keyring
boto3
```

Standard library:

```text
tkinter
json
argparse
subprocess
os
sys
pathlib
datetime
secrets
string
typing
logging
configparser
shlex
```

Optional but avoid in v1:

```text
pydantic
click/typer
cryptography
python-dotenv
pyperclip
```

For clipboard, Tkinter can handle clipboard operations, so avoid `pyperclip`.

For `.env` parsing, write a small conservative parser. Do not add `python-dotenv` unless needed.

## 15. Suggested architecture

```text
devsecrets/
  __init__.py
  app.py                 # Tkinter entrypoint
  cli.py                 # argparse CLI
  model.py               # SecretMap, refs, validation
  backends/
    base.py
    os_keyring.py
    aws_secrets_manager.py
  services/
    index_store.py
    dotenv_parser.py
    codegen.py
    runner.py
    clipboard.py
    audit.py
    aws_policy.py
  ui/
    main_window.py
    folder_panel.py
    secret_editor.py
    actions_panel.py
    dialogs.py
  sdk/
    __init__.py
    client.py
```

## 16. Security posture

Honest threat model:

Protects against:

- accidental Git commits of `.env`
- plaintext secrets sitting in random files
- secrets in Notepad
- secrets copied repeatedly into shell scripts
- local project folders full of credentials
- casual shoulder surfing via masked UI
- some clipboard exposure via timeout

Does **not** fully protect against:

- malware running as the same user
- compromised Python process
- debugger/memory scraping
- malicious shell profile
- malicious package imported by the app
- AWS identity compromise
- clipboard manager history unless clearing works
- terminal scrollback if user prints secrets

The app should say this plainly.

## 17. MVP phases

### Phase 1: Local OS keyring + GUI CRUD

- Tkinter GUI
- OS keyring backend
- local non-secret index
- folders
- default folder
- create/edit/delete secret maps
- masked values
- reveal/copy with timeout
- import `.env`
- generate Python/keyring snippet
- generate `devsecrets run` command

### Phase 2: CLI

- `list`
- `get`
- `set`
- `run`
- `import-env`
- `export-env` with scary flag
- `health`

### Phase 3: AWS first-class backend

- AWS profile selector
- list/create/edit AWS secrets
- JSON `SecretString`
- naming convention
- IAM policy generator
- AWS health check
- sync OS ↔ AWS

### Phase 4: Developer code generation

- Bash
- Python
- Node
- TypeScript
- Java
- Docker
- Docker Compose
- raw AWS SDK snippets
- local `devsecrets run` snippets

### Phase 5: polish

- diff secret maps
- redacted export
- rotation reminders
- key naming lint
- stale secret detection
- recent usage log
- backup of non-secret index
- Linux backend diagnostics

## 18. The product opinion

The winning opinion is:

> A secret manager for developers should not merely store secrets. It should make the safe path the easiest path from inside the developer’s actual workflow.

So the app should constantly steer toward:

```bash
devsecrets run project/dev -- command
```

and:

```python
get_secret_map("project/dev")
```

while still allowing:

```text
copy password
```

because the real world has pgAdmin, AWS consoles, SaaS dashboards, and annoying admin UIs.

## Next 5 questions

1. Should this be **open source local-only software**, or are you imagining a paid/pro version later? It's gonna always be free.

1. Should the app include its own tiny Python SDK package, e.g. `devsecrets-sdk`, or should generated code only use raw `keyring` / `boto3`? It should generate code that does not reference the tool itself.

1. For AWS, do you want one secret per map as JSON, or one AWS secret per individual key? Encourage people to stuff a whole connection string into a json document. Discourage deeply nested json documents. A single key value pair should still be json in storage.

1. Should the OS keyring and AWS versions be treated as separate stores, or should the app encourage **syncing/mirroring** between them? Uh, no mirroring feature yet.

1. Should secret maps support environments as a special concept, like `/project/dev`, `/project/staging`, `/project/prod`, or should environments just be folders by convention? Yeah, I guess so.

And more spec talk

Steal these patterns shamelessly:

From aws-vault:

devsecrets run folder/name -- command

From chamber:

devsecrets write service KEY value
devsecrets exec service -- command

From SOPS:

devsecrets import-env
devsecrets edit
devsecrets diff

From KeePassXC:

masked values
temporary reveal
copy with timeout
search
groups/folders

From Infisical/Doppler/1Password:

developer docs/code snippets are a product feature, not an afterthought

From keyring:

## do not invent local crypto if the OS already gives you a credential store

Also, this app is going to be kind of like aws-vault, bug in python and with a gui.
