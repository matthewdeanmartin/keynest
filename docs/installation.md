# Installation

keynest requires Python 3.11 or newer. Install it as an isolated global tool so its dependencies do not mix with a
project environment.

## Recommended: uv

```console
uv tool install keynest
```

This installs both `keynest` and `keynest-gui` on uv's tool path. If the commands are not found, run `uv tool update-shell`
and open a new terminal. Upgrade or remove the tool with:

```console
uv tool upgrade keynest
uv tool uninstall keynest
```

For a one-off CLI invocation without a persistent installation, use `uvx keynest --help`. A persistent tool install
is more convenient for the GUI and daily use.

## Recommended alternative: pipx

```console
pipx install keynest
```

pipx also installs the two commands in an isolated environment. Use `pipx ensurepath` if they are not on `PATH`.

```console
pipx upgrade keynest
pipx uninstall keynest
```

## Plain pip

Plain pip works, but an isolated tool installation is preferred:

```console
pip install keynest
```

## From source

For development, this repository uses uv for every Python command:

```console
git clone https://github.com/matthewdeanmartin/keynest.git
cd keynest
uv sync --all-extras
uv run keynest --help
```

## Verify the installation

```console
keynest --version
keynest diagnostics
keynest health
```

`health` performs a temporary write/read/delete round trip in the active OS keyring. To launch the desktop interface,
run `keynest-gui`.

On Linux, Tkinter and the desktop credential service are often distribution packages rather than Python packages.
Install your distribution's Tk support and use a logged-in Secret Service or KWallet session. Headless installations
may have no usable native keyring.
