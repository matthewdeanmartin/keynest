# Quick Start

Install keynest with an isolated tool manager:

```console
uv tool install keynest
# or: pipx install keynest
```

Check the local credential store, then create a map:

```console
keynest health
keynest set my-app/dev DATABASE_URL "postgresql://localhost/app"
keynest set my-app/dev LOG_LEVEL info
keynest list
```

`set` is convenient for a demonstration, but a real secret passed as an argument may remain in shell history. Use
`keynest-gui` for interactive entry.

Run an application with the map injected into its child environment:

```console
keynest run my-app/dev -- python app.py
```

The current shell is unchanged and keynest does not write a `.env` file. The child process receives the values and
must be trusted.

Other useful first commands:

```console
keynest lint my-app/dev
keynest redact-export my-app/dev
keynest print-code my-app/dev
keynest recent
```

For AWS, first read the [AWS guide](../aws.md), then select AWS on each command:

```console
keynest health --aws --profile personal --region us-east-1
keynest list --aws --profile personal --region us-east-1
```

Continue with the complete [CLI reference](cli.md), [GUI guide](gui.md), or [storage concepts](../concepts.md).
