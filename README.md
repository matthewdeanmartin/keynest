# keynest

Developer keystore that is pipx-installable and supports the OS keychain / credential
manager and AWS Secrets Manager — with both a CLI and a Tkinter GUI.

keynest is a **developer secret workbench**. It helps a single developer stop scattering
secrets across Notepad, stray `.env` files, shell history, and repo-adjacent config. It
manages *secret maps* (JSON dictionaries of keys to values) in either the laptop OS secret
store (via Python [`keyring`](https://pypi.org/project/keyring/)) or
[AWS Secrets Manager](https://aws.amazon.com/secrets-manager/) (via `boto3`).

The guiding opinion: **make the safe path the easy path.** Instead of

```bash
export DATABASE_PASSWORD=...
```

prefer

```bash
keynest run my-app -- python app.py
```

See [spec/spec.md](spec/spec.md) for the full product specification.

## Prior Art

[aws-vault](https://github.com/ByteNess/aws-vault) is the best prior art and is recommended
over this tool for the moment. The main advantage of keynest will be that it is pure Python
and ships a GUI. keynest also borrows patterns shamelessly from `chamber`, SOPS, KeePassXC,
and the developer-docs-as-a-feature approach of Infisical / Doppler / 1Password.

## Installation

```bash
pipx install keynest
```

Or with pip:

```bash
pip install keynest
```

## Usage

```bash
keynest --help
```

> Note: keynest is in early development. The CLI and GUI described in the
> [spec](spec/spec.md) are not yet implemented — the package scaffold and quality gates
> are in place first.

## Contributing

See [CONTRIBUTING.md](docs/extending/CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).

## Changelog

See [CHANGELOG.md](CHANGELOG.md).
