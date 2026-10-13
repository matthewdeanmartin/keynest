# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Requires Python 3.11 or newer; Python 3.10 is no longer supported.


## [0.1.0] - 2026-07-01
### Added
- Wired `do_i_need_to_upgrade` into normal `keynest` execution so update notices can appear during GUI startup and shutdown without a separate updater CLI
- Added integrated `keynest upgrade` and `keynest check-updates` subcommands; `check-updates --help` documents the scripting exit codes (0/10/1) and the `DO_I_NEED_TO_UPGRADE=off` kill switch
- GUI surfaces update notices: cached notice in the status bar at launch, and a Help → "Check for updates..." menu item that checks PyPI off the main thread
- New `keynest delete` (confirmation prompt, `--yes`, `--dry-run`) and `keynest rename` subcommands, matching the GUI's delete/rename actions
- New `keynest os-credentials` subcommand listing OS credentials from other apps (service/username only; values are never read)
- Transparent repo relocation: detect the git repo (via `.git/config`, no `git` binary) and default a secret map's folder to its `owner.repo` identity (GitHub/GitLab/GHE remotes, SSH and HTTPS; credentials in remote URLs are scrubbed). Stores no secrets in the working tree; only the default folder and view change
- GUI pre-selects the detected repo folder with a dismissible banner and a "Use /default instead" escape hatch; new maps, quick-add, and paste-`.env` default to the repo folder
- CLI resolves a bare map name (no folder) against the detected repo folder; explicit paths always win; `--no-repo` / `KEYNEST_NO_REPO` disable it, and mutating commands echo the resolved `→ /folder/name` path
- Diagnostics report the detected repo, its default folder, and the (scrubbed) remote URL
- Optional committed `.keynest` marker file that maps a repo to an explicit folder (and optional `default_map`); it is secret-free by construction — unknown keys are rejected on read and cannot be written — and overrides inferred identity. New `keynest init-repo` command creates it
- `[tool.keynest]` section in `pyproject.toml` is now read as a higher-priority config source than `.keynest`; same secret-free schema applies

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
