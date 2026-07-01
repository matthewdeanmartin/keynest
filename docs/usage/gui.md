# Desktop GUI

Start the Tkinter application with:

```console
keynest-gui
```

The window has a backend/folder/map browser on the left, a masked key/value editor in the middle, and common actions
on the right. It starts in OS-keyring mode. Selecting AWS Secrets Manager opts into AWS network and credential access;
the default “All” view still queries only the OS keyring on startup.

If launched inside a Git repository, the GUI adds and preselects a folder derived from that repository. New maps,
quick-added passwords, and pasted `.env` content use the selected repo folder. The banner's **Use /default instead**
button disables that default for the current session. See [repository-aware defaults](../repositories.md).

## Creating and editing maps

- **Quick add password** creates `<selected-folder>/<name>` containing one key named `VALUE`; it can generate a random
  value.
- **Paste .env** previews and merges pasted `KEY=value` lines into a chosen map.
- **New map** starts an empty map in the selected folder and backend; add keys and save it.
- Select a row to edit, rename, or delete a key, reveal it temporarily, copy it, or replace it with a generated
  24-character password.
- Description and comma-separated tags are stored with OS-keyring index metadata. They are not currently persisted by
  the AWS backend.
- Map controls can rename/move, duplicate, or delete a whole map. OS deletion is immediate; AWS deletion is scheduled
  with a seven-day recovery window despite the GUI's generic confirmation wording.

Values are masked only in the interface; masking is not encryption. Revealed values remain in application memory.
Copy places a value in the shared OS clipboard and schedules a clear after 30 seconds. The clear occurs only if the
clipboard still contains the value keynest copied, so it will not erase newer clipboard content. Clipboard managers,
other applications, and malware may still observe the value before it clears.

## Using maps

The GUI shows the recommended `keynest run` terminal command but does not launch arbitrary processes itself. The code
viewer provides the same templates as `keynest print-code`. Import updates the in-memory map and requires **Save**;
export writes a plaintext `.env` after an explicit warning.

Tools include lint, key-only diff, redacted JSON, stale local maps, recent activity, diagnostics, and index backup.
The Backend menu provides health checks, policy generation, and the AWS setup wizard. The GUI's **Health check**
currently checks only the OS keyring; use the wizard or `keynest health --aws` to check AWS. See the
[CLI guide](cli.md) and [AWS guide](../aws.md) for exact behavior and limitations shared by those features.

## Other OS credentials

**Show all OS credentials (names only)** asks supported native keyring backends to enumerate service and username
identifiers. Other applications' credentials appear under the read-only `(os credentials)` folder. keynest does not
display or retain their values and does not offer edit, copy, rename, or delete actions for them; it can only show the
identifiers and generate explicit raw-keyring lookup examples. On Windows, the underlying `CredEnumerate` result may
contain credential blobs that keynest ignores; see [credential discovery](../concepts.md#credential-discovery).

The view is unavailable when the active backend cannot enumerate. Windows Credential Manager, macOS Keychain, Linux
Secret Service, and Linux libsecret have implementations; KWallet and other backends currently return no rows.

## Linux desktop requirements

Tkinter and a usable keyring service are separate requirements. A distribution may require its Tk package plus a
running Secret Service (such as GNOME Keyring) or KWallet session. Headless or SSH sessions commonly select a null or
failing keyring. Run `keynest diagnostics` to see what Python keyring selected.
