# keynest

Developer secret workbench: a pure-Python keystore with a CLI and a Tkinter GUI for the
OS keyring and AWS Secrets Manager.

keynest manages **secret maps** — flat JSON dictionaries of scalar values — stored
in either the laptop OS secret store (via `keyring`) or AWS Secrets Manager (via `boto3`).
Its goal is to make safe usage paths (`keynest run`, generated SDK code) easier than unsafe
ones (exporting plaintext `.env` files, pasting into shell history).

It is aimed at one developer who wants less plaintext sprawl without deploying a service. It is not a team vault,
password manager, rotation system, or access-control layer. Start with the [documentation home](../index.md), then see
[concepts and storage](../concepts.md) for the data model and current limitations. The repository's
[specification](https://github.com/matthewdeanmartin/keynest/blob/main/spec/spec.md) records product history and intent;
these user documents describe the implemented behavior.
