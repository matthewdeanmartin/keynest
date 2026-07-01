# Repository-aware defaults

When a keynest command runs inside a Git working tree, a bare map name is resolved in a folder associated with that
repository. This lets short commands follow a checkout when it is cloned or moved:

```console
# In a checkout whose origin is github.com/acme/payments:
keynest set dev API_TOKEN value
# resolves to /acme.payments/dev

keynest run dev -- python app.py
```

This feature changes only path resolution. keynest does not put secret values, an index, or an audit log in the
repository.

## How the folder is chosen

keynest walks from the current directory to the nearest `.git` directory or worktree pointer, then applies this order:

1. Use the `folder` in a valid `[tool.keynest]` section of `pyproject.toml` at the repository root.
1. Otherwise use the `folder` in a valid `.keynest` marker at the repository root.
1. Otherwise, read the preferred remote from `.git/config` (`origin`, or the first remote) and derive `owner.repo`.
   GitLab-style subgroups are flattened with dots.
1. If no usable remote exists, use the working-tree directory name.

Detection reads Git metadata directly; it does not invoke the `git` executable. HTTPS credentials embedded in a
remote URL are removed before the URL is exposed by diagnostics. Detection failures fall back to ordinary path
behavior.

An explicit path such as `default/dev` or `another-project/dev` always wins. Outside a repository, a bare `dev`
continues to mean `/default/dev`.

## The `pyproject.toml` integration

If your project already has a `pyproject.toml`, you can place the keynest configuration there instead of
creating a separate `.keynest` file. Add a `[tool.keynest]` section:

```toml
[tool.keynest]
folder = "acme.payments"
default_map = "dev"       # optional
```

The same secret-free schema applies: only `folder` and optional `default_map` are accepted. An unknown key
causes the section to be ignored and detection falls through to the next source.

When both `pyproject.toml` and `.keynest` are present, `[tool.keynest]` in `pyproject.toml` wins.

## The `.keynest` marker

Create a marker when a team wants a stable folder that does not depend on a developer's remote URL or directory name:

```console
keynest init-repo --folder acme.payments --default-map dev
```

The generated `.keynest` is TOML:

```toml
folder = "acme.payments"
default_map = "dev"
```

It is designed to be committed. Only `folder` and optional `default_map` keys are accepted; `init-repo` cannot produce
other fields. A manually edited marker with an unknown key is invalid and automatic detection ignores it, then falls
back to the remote or directory name. The generated file contains routing names, not secrets, though project and
environment names may still be sensitive metadata.

`default_map` fills a missing name when the CLI receives an empty path or a folder-only path such as `staging/`. Most
normal usage can simply pass the bare map name.

`init-repo` refuses to overwrite an existing marker unless `--force` is supplied. `--dry-run` reports what it would
write without creating the file.

## Disabling the behavior

Pass `--no-repo` after the subcommand to disable detection for one invocation:

```console
keynest run --no-repo dev -- python app.py
```

Set `KEYNEST_NO_REPO` to any non-empty value to disable it for CLI invocations in that environment. The GUI instead
shows the detected repo in a banner; **Use /default instead** disables its repo default for the current GUI session.

Mutating CLI commands print the resolved path to standard error when repo defaulting was applied, so a write does not
silently land in an inferred folder.
