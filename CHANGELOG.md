# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.1] - 2026-06-30
### Added
- Secret map model with folders, default folder, and Bash-compatible key validation
- OS keyring backend storing secret maps as JSON, with a local non-secret index
- AWS Secrets Manager backend (one JSON secret per map, ManagedBy tags)
- Local index store with non-secret metadata and timestamped backup
- `.env` parser and serializer (no third-party dependencies)
- Code generator for Bash, Python, Node/TypeScript, Java, Docker, and Docker Compose
- Subprocess runner that injects secrets into a child environment without writing to disk
- Clipboard helper with configurable auto-clear timeout
- Append-only audit log of usage events (never values)
- AWS IAM least-privilege policy generator
- Secret value generators and validators (password, hex, base64, UUID, URL, JSON, PEM)
- Repo hygiene tools: scan for `.env` files and suggest `.gitignore` entries
- AWS setup wizard (detect, identity, ListSecrets probe, test secret lifecycle, policy)
- Map tools: diff, redacted export, JSON import/export, lint, staleness, rotation, duplicate
- Environment diagnostics reporting keyring backend, platform, and store health
- CLI: list, get, set, run, print-code, import-env, export-env, aws-policy, health, aws-setup
- CLI: diff, lint, stale, redact-export, duplicate, recent, diagnostics, backup-index
- Global `--dry-run` flag describing side effects without performing them
- Tkinter three-panel GUI with folders, masked key/value editor, and usage actions
- GUI map create, edit, delete, rename, and duplicate
- GUI AWS setup wizard dialog and IAM policy generator
- GUI tools for lint, diff, redacted export, stale maps, recent activity, diagnostics, and index backup
- GUI quick-add password dialog (name plus value)
- GUI paste-`.env` dialog for bulk entry
- `keynest` CLI and `keynest-gui` console scripts
