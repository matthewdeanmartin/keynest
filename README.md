# keynest

Why? Because you're going to leak your .env files to git someday.

keynest is a local-first secret workbench for individual developers. It keeps named maps (json files) of configuration
in your operating system's credential store or AWS Secrets Manager and makes the safest common operation the shortest
one:

```console
keynest run dev -- python app.py
```

The values are added only to that child process's environment. Your current shell is unchanged and keynest does not
create a plaintext `.env` file.

keynest is useful when you:

- switch among several projects or environments and want each one's values grouped together;
- want a lightweight GUI for entering, masking, copying, and organizing development credentials;
- need the same CLI workflow with either a laptop keychain or AWS Secrets Manager;
- inherited a `.env` file and want to import it, then stop keeping the working copy in the repository; or
- want repo-aware defaults so `keynest run dev -- ...` finds the right map after you move or clone a checkout.

## How it compares

| Tool category | Better fit when | How keynest differs |
|--------------------------|----------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------|
| `.env` files | Portability and framework-native loading matter more than plaintext-at-rest risk | keynest avoids a working plaintext file and injects values at process launch |
| Password managers | You need browser autofill, personal records, sharing, or polished mobile apps | keynest organizes flat environment-style maps and focuses on developer processes |
| Team secret platforms | You need sharing, access policy, rotation, approvals, or centralized audit | keynest is deliberately single-developer and has no server of its own |
| Cloud-only secret stores | Production workloads already fetch secrets directly from a cloud provider | keynest adds a local OS-keyring option, a GUI, and one workflow across local and AWS storage |

keynest is alpha software. It reduces accidental exposure through files, commits, shell exports, and casual display;
it is not a boundary against malware, a compromised user account, or an untrusted child process.

## Installation

Python 3.11 or newer is required. An isolated tool installation is recommended:

```console
uv tool install keynest
# or
pipx install keynest
```

Plain pip also works:

```console
pip install keynest
```

The package installs `keynest` and `keynest-gui`. Linux users may also need their distribution's Tkinter package and
a running Secret Service or KWallet session.

## Quick start

Check that the OS credential store works, then create a map:

```console
keynest health
keynest set my-app/dev DATABASE_URL "postgresql://localhost/app"
keynest set my-app/dev LOG_LEVEL info
keynest run my-app/dev -- python app.py
```

Passing a real secret to `set` can leave it in shell history, so use `keynest-gui` for interactive entry. The GUI can
also import pasted `.env` content, generate passwords, reveal or copy values temporarily, and manage maps.

Inside a Git checkout, a bare map name defaults to a folder derived from the remote, such as
`/acme.my-app/dev`. An explicit `folder/name` always wins:

```console
keynest set dev API_TOKEN value       # detected repo folder, if any
keynest set default/dev API_TOKEN value
keynest run dev -- npm run dev
```

Use `keynest init-repo` to create a secret-free `.keynest` marker with a stable folder choice, or pass `--no-repo` to
disable repo-aware resolution for one command.

AWS Secrets Manager is selected per command:

```console
keynest health --aws --profile personal --region us-east-1
keynest run --aws --profile personal --region us-east-1 dev -- python app.py
```

Run `keynest --help` for all commands. The full documentation covers the [quick start](docs/usage/quickstart.md),
[CLI](docs/usage/cli.md), [GUI](docs/usage/gui.md), [repository defaults](docs/repositories.md),
[storage model](docs/concepts.md), [AWS backend](docs/aws.md), and [security limitations](docs/security.md).

## Contributing

See [CONTRIBUTING.md](docs/extending/CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## Prior Art

[aws-vault](https://github.com/ByteNess/aws-vault) is the best prior art and is recommended
over this tool for the moment. The main advantage of keynest will be that it is pure Python
and ships a GUI. keynest also borrows patterns shamelessly from `chamber`, SOPS, KeePassXC,
and the developer-docs-as-a-feature approach of Infisical / Doppler / 1Password.
