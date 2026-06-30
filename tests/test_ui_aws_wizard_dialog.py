"""Light integration tests for the AWS wizard Tk dialog."""

from __future__ import annotations

from keynest.services.aws_wizard import WizardStep
from keynest.ui.aws_wizard import AwsWizardDialog


def test_show_renders_steps_and_policy(tk_root):
    dialog = AwsWizardDialog(tk_root)
    steps = [
        WizardStep("detect", True, "found boto3"),
        WizardStep("identity", True, "Account 123"),
        WizardStep("policy", True, "ok", {"policy": "{POLICY-JSON}"}),
    ]
    dialog._show(steps)
    shown = dialog._results.get("1.0", "end")
    assert "[OK  ] detect" in shown
    assert "{POLICY-JSON}" in shown
    # Policy present -> Copy button enabled.
    assert str(dialog._copy_button.cget("state")) == "normal"
    dialog.destroy()


def test_show_failure_marks_fail(tk_root):
    dialog = AwsWizardDialog(tk_root)
    dialog._show([WizardStep("identity", False, "no creds")])
    shown = dialog._results.get("1.0", "end")
    assert "[FAIL] identity: no creds" in shown
    assert dialog._policy_text is None
    dialog.destroy()


def test_copy_policy_puts_text_on_clipboard(tk_root):
    dialog = AwsWizardDialog(tk_root)
    dialog._show([WizardStep("policy", True, "ok", {"policy": "POLICY-BODY"})])
    dialog._copy_policy()
    assert tk_root.clipboard_get() == "POLICY-BODY"
    dialog.destroy()


def test_profile_dropdown_includes_default(tk_root):
    dialog = AwsWizardDialog(tk_root)
    assert dialog._profile_var.get().startswith("(")  # "(default chain)"
    dialog.destroy()
