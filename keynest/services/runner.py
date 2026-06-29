"""Run a subprocess with a secret map injected into its environment.

This is the headline safe-usage workflow: secrets are merged into the child
process environment only, never written to disk or printed.
"""

from __future__ import annotations

import os
import subprocess  # nosec B404 - launching the user's chosen command is the feature

from keynest.model import SecretMap


def build_environment(secret_map: SecretMap, base_env: dict[str, str] | None = None) -> dict[str, str]:
    """Return a copy of ``base_env`` with the secret map's values merged in.

    Non-string scalar values are coerced to strings (subprocess env requires str).

    Args:
        secret_map: The secret map whose values to inject.
        base_env: The starting environment (defaults to the current ``os.environ``).

    Returns:
        A new environment dictionary suitable for :func:`subprocess.run`.
    """
    env = dict(os.environ if base_env is None else base_env)
    for key, value in secret_map.values.items():
        if value is None:
            continue
        env[key] = value if isinstance(value, str) else str(value)
    return env


def run_with_secrets(
    secret_map: SecretMap,
    command: list[str],
    base_env: dict[str, str] | None = None,
) -> int:
    """Run ``command`` with ``secret_map`` injected into the environment.

    Args:
        secret_map: Secrets to inject.
        command: The command and arguments to execute (``argv``-style list).
        base_env: Optional base environment.

    Returns:
        The child process exit code.

    Raises:
        ValueError: If ``command`` is empty.
    """
    if not command:
        raise ValueError("No command given to run.")
    env = build_environment(secret_map, base_env)
    completed = subprocess.run(command, env=env, check=False)  # nosec B603 - intentional user command
    return completed.returncode
