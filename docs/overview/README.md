# keynest

Developer secret workbench: a pure-Python keystore with a CLI and a Tkinter GUI for the
OS keyring and AWS Secrets Manager.

keynest manages **secret maps** — JSON dictionaries of keys to secret-ish values — stored
in either the laptop OS secret store (via `keyring`) or AWS Secrets Manager (via `boto3`).
Its goal is to make safe usage paths (`keynest run`, generated SDK code) easier than unsafe
ones (exporting plaintext `.env` files, pasting into shell history).

See the [spec](https://github.com/matthewdeanmartin/keynest/blob/main/spec/spec.md) for the
full product specification and MVP phases.
