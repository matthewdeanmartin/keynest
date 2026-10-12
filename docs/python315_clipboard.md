# Local finding for human review: Tk clipboard crash with an unrealized hidden window

No upstream report has been filed. The human operator chooses whether to file, where, and what change to propose.

Observed on Windows x64 in uv-managed CPython 3.15.0rc3 and 3.14.7. Exact Tk package versions and output are in `clipboard-*-withdraw.log`; the small probe itself is `clipboard_probe.py`. Both subprocesses terminate with Windows access violation status 3221225477 (0xC0000005).

Minimal reproduction, requiring no third-party Python package:

```python
import tkinter as tk
root = tk.Tk()
print(root.tk.call('package', 'provide', 'Tk'), flush=True)
root.withdraw()
root.clipboard_clear()
root.destroy()
```

Expected: clear the clipboard or raise a Python/Tcl exception. Observed: process crashes in native code. The full keynest suite and isolated clipboard-only suite reproduce it. It occurs on 3.14 as well, so it is not established as a new Python 3.15 regression.

Controls: insert `root.winfo_id()` before `clipboard_clear()` and the subprocess exits successfully. Inserting `root.update_idletasks()` also passes. The former realizes the native window without mapping it or pumping callbacks and is the smaller local workaround. keynest's ClipboardManager.copy now calls winfo_id before manipulating the clipboard; its existing live clipboard integration tests exercise this hidden-root path.

Likely area to investigate: Windows Tk clipboard handling when a widget's native window has not been realized. This is an inference from the passing controls, not a verified native-code diagnosis. The interpreter's bundled Tk version/distribution may matter. An operator should compare a current official CPython installation or standalone current Tk before choosing a target such as CPython, Tk, or the interpreter distributor. No compiler or toolchain installation is needed for those runtime comparisons.

Suggested upstream behavior: safely realize a required native window, return an informative Tcl error for an unsupported state, or document the precondition; avoid a process crash. Do not assume which project owns the fix or that existing tracker search hits describe this same failure.

Runtime reproduction touches the shared OS clipboard. Use disposable sample data when reproducing it; the observed tests do not involve real stored secrets.
