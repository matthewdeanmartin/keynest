"""Generate developer code snippets for consuming a secret map.

These snippets are the product's wedge: they deliberately reference only raw
``keyring`` / ``boto3`` / cloud SDKs (never a keynest runtime library) so the
generated code has zero dependency on this tool.
"""

from __future__ import annotations

from dataclasses import dataclass

from keynest.model import (
    SERVICE_NAME_HINT,
    RawCredential,
    SecretMap,
    logical_path,
)

# A representative key used in examples, falling back to a placeholder.
_PLACEHOLDER_KEY = "DATABASE_URL"


@dataclass
class Snippet:
    """A named, language-tagged code snippet."""

    title: str
    language: str
    code: str


def _example_key(secret_map: SecretMap) -> str:
    """Pick a representative key for the snippet examples."""
    return secret_map.keys[0] if secret_map.values else _PLACEHOLDER_KEY


def _aws_secret_id(secret_map: SecretMap) -> str:
    """Return the AWS Secrets Manager SecretId for a map."""
    return f"devsecrets/{secret_map.folder}/{secret_map.name}"


def _run_path(secret_map: SecretMap) -> str:
    """Return the ``folder/name`` form used by ``keynest run``."""
    return f"{secret_map.folder}/{secret_map.name}"


# -- bash --------------------------------------------------------------------


def bash_run(secret_map: SecretMap, command: str = "python app.py") -> Snippet:
    """Generate the recommended ``keynest run`` Bash command."""
    return Snippet(
        title="Bash: keynest run (recommended)",
        language="bash",
        code=f"keynest run {_run_path(secret_map)} -- {command}",
    )


def bash_direct(secret_map: SecretMap) -> Snippet:
    """Generate the less-safe direct-lookup Bash escape hatch."""
    key = _example_key(secret_map)
    code = (
        f"# less safe: secret may enter shell history, process args,\n"
        f"# terminal scrollback, or logs depending on usage.\n"
        f'{key}="$(keynest get {_run_path(secret_map)} {key})"'
    )
    return Snippet(title="Bash: direct lookup (less safe)", language="bash", code=code)


# -- python ------------------------------------------------------------------


def python_keyring(secret_map: SecretMap) -> Snippet:
    """Generate raw ``keyring`` Python for the OS keyring backend."""
    key = _example_key(secret_map)
    path = logical_path(secret_map.folder, secret_map.name)
    code = (
        "import json\n"
        "import keyring\n\n"
        "payload = keyring.get_password(\n"
        f'    "{SERVICE_NAME_HINT}",\n'
        f'    "{path}",\n'
        ")\n"
        "if payload is None:\n"
        f'    raise RuntimeError("Secret map not found: {path}")\n\n'
        "secrets = json.loads(payload)\n"
        f'{key.lower()} = secrets["{key}"]'
    )
    return Snippet(title="Python: raw keyring", language="python", code=code)


def python_boto3(secret_map: SecretMap) -> Snippet:
    """Generate raw ``boto3`` Python for the AWS backend."""
    key = _example_key(secret_map)
    code = (
        "import json\n"
        "import boto3\n\n"
        'client = boto3.client("secretsmanager")\n'
        f'response = client.get_secret_value(SecretId="{_aws_secret_id(secret_map)}")\n'
        'secrets = json.loads(response["SecretString"])\n\n'
        f'{key.lower()} = secrets["{key}"]'
    )
    return Snippet(title="Python: raw boto3 (AWS)", language="python", code=code)


# -- node / typescript -------------------------------------------------------


def node_aws(secret_map: SecretMap) -> Snippet:
    """Generate Node/TypeScript using the AWS SDK v3."""
    key = _example_key(secret_map)
    camel = _to_camel(key)
    code = (
        'import { SecretsManagerClient, GetSecretValueCommand } from "@aws-sdk/client-secrets-manager";\n\n'
        "const client = new SecretsManagerClient({});\n"
        "const response = await client.send(\n"
        f'  new GetSecretValueCommand({{ SecretId: "{_aws_secret_id(secret_map)}" }})\n'
        ");\n\n"
        "if (!response.SecretString) {\n"
        '  throw new Error("SecretString was empty");\n'
        "}\n\n"
        "const secrets = JSON.parse(response.SecretString);\n"
        f"const {camel} = secrets.{key};"
    )
    return Snippet(title="Node/TypeScript: AWS SDK", language="typescript", code=code)


def node_run(secret_map: SecretMap, command: str = "npm run dev") -> Snippet:
    """Generate the recommended ``keynest run`` wrapper for Node."""
    return Snippet(
        title="Node/TypeScript: keynest run (recommended for local)",
        language="bash",
        code=f"keynest run {_run_path(secret_map)} -- {command}",
    )


# -- java --------------------------------------------------------------------


def java_aws(secret_map: SecretMap) -> Snippet:
    """Generate Java using the AWS SDK v2."""
    code = (
        "SecretsManagerClient client = SecretsManagerClient.create();\n\n"
        "GetSecretValueResponse response = client.getSecretValue(\n"
        "    GetSecretValueRequest.builder()\n"
        f'        .secretId("{_aws_secret_id(secret_map)}")\n'
        "        .build()\n"
        ");\n\n"
        "String json = response.secretString();"
    )
    return Snippet(title="Java: AWS SDK", language="java", code=code)


def java_run(secret_map: SecretMap, command: str = "./gradlew bootRun") -> Snippet:
    """Generate the recommended ``keynest run`` wrapper for Java."""
    return Snippet(
        title="Java: keynest run (recommended for local)",
        language="bash",
        code=f"keynest run {_run_path(secret_map)} -- {command}",
    )


# -- docker ------------------------------------------------------------------


def docker_run(secret_map: SecretMap, image: str = "my-image") -> Snippet:
    """Generate a ``docker run`` command wrapped by ``keynest run``."""
    code = f"keynest run {_run_path(secret_map)} -- docker run --rm -e {{vars}} {image}"
    var_flags = " ".join(f"-e {k}" for k in secret_map.keys) or "-e DATABASE_URL"
    code = code.replace("{vars}", var_flags)
    return Snippet(title="Docker: run wrapped", language="bash", code=code)


def docker_compose(secret_map: SecretMap, service: str = "app") -> Snippet:
    """Generate a Docker Compose snippet whose env is supplied by the runtime wrapper."""
    env_lines = "\n".join(f"      - {k}" for k in secret_map.keys) or "      - DATABASE_URL"
    yaml = (
        "services:\n"
        f"  {service}:\n"
        "    image: my-image\n"
        "    environment:\n"
        f"{env_lines}\n\n"
        "# Launch so the variables above are populated from the secret map:\n"
        f"#   keynest run {_run_path(secret_map)} -- docker compose up"
    )
    return Snippet(title="Docker Compose: runtime wrapper", language="yaml", code=yaml)


# -- manual ------------------------------------------------------------------


def manual_checklist(secret_map: SecretMap) -> Snippet:
    """Generate a copy/paste checklist for manual admin UIs (e.g. pgAdmin)."""
    key = _example_key(secret_map)
    code = (
        "Manual copy checklist (pgAdmin / dashboards):\n"
        f"  1. Open {secret_map.path} in keynest.\n"
        f"  2. Copy {key} (auto-clears from clipboard after the timeout).\n"
        "  3. Paste into the target field.\n"
        "  4. Avoid pasting into chat, tickets, or logs.\n"
        "  Prefer `keynest run` or generated SDK code when the tool supports it."
    )
    return Snippet(title="Manual: copy checklist", language="text", code=code)


# -- raw (non-keynest) OS credentials ----------------------------------------


def raw_python_keyring(cred: RawCredential) -> Snippet:
    """Generate raw ``keyring`` Python for a non-keynest OS credential.

    Unlike keynest maps, this credential's value is opaque: keynest did not
    write it, so there is no JSON structure to parse. The snippet returns the
    raw string exactly as the owning application stored it.
    """
    user = cred.username or ""
    code = (
        "import keyring\n\n"
        "# This credential was NOT created by keynest. Its value is opaque:\n"
        "# whatever the owning application stored (string, JSON, token, etc.).\n"
        "value = keyring.get_password(\n"
        f"    {cred.service!r},\n"
        f"    {user!r},\n"
        ")\n"
        "if value is None:\n"
        f'    raise RuntimeError("Credential not found: {cred.service}")\n'
        "# `value` is the raw secret; parse it yourself if it has structure."
    )
    return Snippet(title="Python: raw keyring (opaque value)", language="python", code=code)


def raw_bash(cred: RawCredential) -> Snippet:
    """Generate a Bash one-liner reading a non-keynest OS credential."""
    user = cred.username or ""
    code = (
        "# Opaque credential not managed by keynest; value printed as stored.\n"
        "# less safe: the secret may enter shell history/scrollback/logs.\n"
        f'python -c "import keyring; print(keyring.get_password({cred.service!r}, {user!r}))"'
    )
    return Snippet(title="Bash: raw keyring (less safe)", language="bash", code=code)


def raw_snippets(cred: RawCredential) -> list[Snippet]:
    """Generate the snippet set for a raw, non-keynest OS credential."""
    return [raw_python_keyring(cred), raw_bash(cred)]


def _to_camel(name: str) -> str:
    """Convert ``DATABASE_URL`` to ``databaseUrl`` for JS variable names."""
    parts = name.lower().split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def all_snippets(secret_map: SecretMap) -> list[Snippet]:
    """Generate the full set of snippets appropriate for a secret map.

    Backend-specific snippets are selected based on ``secret_map.backend`` but
    both raw-backend variants are always offered for reference.

    Args:
        secret_map: The map to generate snippets for.

    Returns:
        An ordered list of :class:`Snippet` objects, recommended paths first.
    """
    snippets = [
        bash_run(secret_map),
        python_keyring(secret_map),
        python_boto3(secret_map),
        bash_direct(secret_map),
        node_aws(secret_map),
        node_run(secret_map),
        java_aws(secret_map),
        java_run(secret_map),
        docker_run(secret_map),
        docker_compose(secret_map),
        manual_checklist(secret_map),
    ]
    return snippets
