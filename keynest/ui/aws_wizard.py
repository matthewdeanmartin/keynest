"""Tkinter dialog driving the AWS setup wizard.

Lets the user pick a profile/region, runs the wizard steps on a worker thread
(so AWS calls don't freeze the UI), shows each step's result, and displays the
generated IAM policy.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from keynest.backends.aws_secrets_manager import available_profiles
from keynest.services.aws_wizard import AwsSetupWizard, WizardStep


class AwsWizardDialog(tk.Toplevel):
    """A modal dialog that runs the AWS setup wizard and reports results."""

    def __init__(self, parent: tk.Misc) -> None:
        """Build the wizard UI as a child of ``parent``."""
        super().__init__(parent)
        self.title("AWS setup wizard")
        self.geometry("720x560")
        self.transient(parent)  # type: ignore[call-overload]  # tk stub is over-narrow

        intro = (
            "Checks your AWS identity, probes ListSecrets, creates then schedules "
            "deletion of a throwaway secret at devsecrets/default/test, and "
            "generates a least-privilege IAM policy."
        )
        ttk.Label(self, text=intro, wraplength=680, justify="left").pack(anchor="w", padx=10, pady=(10, 6))

        form = ttk.Frame(self)
        form.pack(fill="x", padx=10)
        ttk.Label(form, text="Profile:").grid(row=0, column=0, sticky="w")
        profiles = ["(default chain)", *available_profiles()]
        self._profile_var = tk.StringVar(value=profiles[0])
        ttk.Combobox(form, textvariable=self._profile_var, values=profiles, state="readonly", width=28).grid(
            row=0, column=1, sticky="w", padx=4, pady=2
        )

        ttk.Label(form, text="Region:").grid(row=1, column=0, sticky="w")
        self._region_var = tk.StringVar(value="")
        ttk.Entry(form, textvariable=self._region_var, width=30).grid(row=1, column=1, sticky="w", padx=4, pady=2)
        ttk.Label(form, text="(blank = resolve from profile/env)").grid(row=1, column=2, sticky="w")

        self._allow_delete_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self,
            text="Include delete/restore actions in the generated policy",
            variable=self._allow_delete_var,
        ).pack(anchor="w", padx=10, pady=(4, 0))

        self._results = tk.Text(self, wrap="word", height=18, font=("Consolas", 10))
        self._results.pack(fill="both", expand=True, padx=10, pady=8)
        self._results.configure(state="disabled")

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=10, pady=(0, 10))
        self._run_button = ttk.Button(buttons, text="Run wizard", command=self._start)
        self._run_button.pack(side="left")
        self._copy_button = ttk.Button(buttons, text="Copy policy", command=self._copy_policy, state="disabled")
        self._copy_button.pack(side="left", padx=6)
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")

        self._policy_text: str | None = None
        self.grab_set()

    # -- running -------------------------------------------------------------

    def _start(self) -> None:
        """Kick off the wizard on a worker thread."""
        self._run_button.configure(state="disabled")
        self._copy_button.configure(state="disabled")
        self._policy_text = None
        self._set_results("Running...\n")

        profile = None if self._profile_var.get().startswith("(") else self._profile_var.get()
        region = self._region_var.get().strip() or None
        allow_delete = self._allow_delete_var.get()
        wizard = AwsSetupWizard(profile=profile, region=region)

        def worker() -> None:
            steps = wizard.run_all(allow_delete_in_policy=allow_delete)
            # Marshal the result back onto the Tk main thread.
            self.after(0, lambda: self._show(steps))

        threading.Thread(target=worker, daemon=True).start()

    def _show(self, steps: list[WizardStep]) -> None:
        """Render the completed wizard steps."""
        lines: list[str] = []
        for step in steps:
            marker = "OK  " if step.ok else "FAIL"
            lines.append(f"[{marker}] {step.name}: {step.detail}")
            if step.name == "policy" and step.ok:
                self._policy_text = step.data.get("policy")
        text = "\n".join(lines)
        if self._policy_text:
            text += "\n\n--- Suggested IAM policy ---\n" + self._policy_text
            self._copy_button.configure(state="normal")
        self._set_results(text)
        self._run_button.configure(state="normal")

    # -- helpers -------------------------------------------------------------

    def _set_results(self, text: str) -> None:
        self._results.configure(state="normal")
        self._results.delete("1.0", "end")
        self._results.insert("1.0", text)
        self._results.configure(state="disabled")

    def _copy_policy(self) -> None:
        if self._policy_text:
            self.clipboard_clear()
            self.clipboard_append(self._policy_text)
