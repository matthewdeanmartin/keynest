# keynest documentation

keynest is a single-developer secret workbench with a Tkinter desktop interface and a command-line interface. It
stores named maps of values in your operating system's credential store or in AWS Secrets Manager, then helps you use
those values without creating another plaintext file.

The preferred workflow is to inject a map into one child process:

```console
keynest run my-app/dev -- python app.py
```

This is safer than exporting values in a long-lived shell or writing a `.env` file, although the child process still
receives the values in its environment and must be trusted.

## Start here

- [Install keynest](installation.md) as an isolated command-line tool with `uv` or `pipx`.
- Follow the [quick start](usage/quickstart.md) to create and use a secret map.
- Use the [CLI reference](usage/cli.md) for every command and option.
- Read [concepts and storage](concepts.md) to understand secret maps, paths, the local index, and both backends.
- Read the [GUI guide](usage/gui.md) for the three-panel desktop application.
- Configure the [AWS Secrets Manager backend](aws.md) when local OS storage is not enough.
- Review the [security model and limitations](security.md) before relying on keynest for sensitive work.

## What is implemented

keynest can currently:

- create, edit, rename, move, duplicate, list, and delete secret maps in the GUI;
- store maps in the OS keyring or AWS Secrets Manager;
- inject a map into a child process, inspect one value, and import or export `.env` data from the CLI;
- generate Python, shell, Node/TypeScript, Java, Docker, Docker Compose, and manual-use examples;
- compare and lint maps, produce redacted JSON, identify stale local-index entries, and show non-secret recent activity;
- diagnose the active keyring and back up the non-secret local index; and
- generate an AWS IAM policy and exercise AWS setup with a test-secret lifecycle.

keynest is alpha software for one developer. It is not a team vault, password-manager replacement, browser autofill
tool, secret-rotation service, or protection against malicious software already running as your user.
