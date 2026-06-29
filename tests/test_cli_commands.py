"""End-to-end CLI tests using the in-memory keyring."""

from __future__ import annotations

import pytest

from keynest.cli import main


@pytest.fixture(autouse=True)
def _isolate(mem_keyring, devsecrets_home):
    """All CLI tests run against an in-memory keyring and isolated home."""
    return None


def test_set_list_get(capsys):
    assert main(["set", "my-app/dev", "DATABASE_URL", "postgres://x"]) == 0
    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "/my-app/dev" in out

    assert main(["get", "my-app/dev", "DATABASE_URL"]) == 0
    assert capsys.readouterr().out.strip() == "postgres://x"


def test_get_missing_key_returns_2(capsys):
    main(["set", "my-app/dev", "A", "1"])
    capsys.readouterr()
    assert main(["get", "my-app/dev", "MISSING"]) == 2


def test_get_missing_map_returns_2():
    assert main(["get", "nope/nope", "X"]) == 2


def test_run_injects_environment():
    main(["set", "my-app/dev", "KEYNEST_RUNTEST", "yes"])
    rc = main(
        [
            "run",
            "my-app/dev",
            "--",
            "python",
            "-c",
            "import os,sys; sys.exit(0 if os.environ.get('KEYNEST_RUNTEST')=='yes' else 9)",
        ]
    )
    assert rc == 0


def test_export_requires_flag(tmp_path):
    main(["set", "my-app/dev", "A", "1"])
    dest = tmp_path / "out.env"
    assert main(["export-env", "my-app/dev", str(dest)]) == 2
    assert not dest.exists()
    assert main(["export-env", "my-app/dev", str(dest), "--i-understand-this-is-less-safe"]) == 0
    assert "A=1" in dest.read_text()


def test_import_env(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text("A=1\nB=two\n")
    assert main(["import-env", "my-app/dev", str(env)]) == 0
    capsys.readouterr()
    assert main(["get", "my-app/dev", "B"]) == 0
    assert capsys.readouterr().out.strip() == "two"


def test_print_code_python(capsys):
    main(["set", "my-app/dev", "DATABASE_URL", "x"])
    capsys.readouterr()
    assert main(["print-code", "my-app/dev", "--language", "python"]) == 0
    out = capsys.readouterr().out
    assert "import keyring" in out
    assert "import keynest" not in out


def test_aws_policy_with_explicit_account(capsys):
    rc = main(["aws-policy", "--account-id", "123456789012", "--region", "us-east-1", "--folder", "my-app"])
    assert rc == 0
    assert "devsecrets/my-app/*" in capsys.readouterr().out


def test_health_os_keyring(capsys):
    assert main(["health"]) == 0
    assert "os-keyring" in capsys.readouterr().out


def test_aws_setup_yes_runs_wizard(capsys, monkeypatch):
    import keynest.services.aws_wizard as wiz

    calls = {}

    class FakeWizard:
        def __init__(self, profile=None, region=None):
            calls["profile"] = profile
            calls["region"] = region

        def run_all(self, *, allow_delete_in_policy=False):
            calls["allow_delete"] = allow_delete_in_policy
            return [
                wiz.WizardStep("detect", True, "ok"),
                wiz.WizardStep("policy", True, "done", {"policy": "{POLICY-JSON}"}),
            ]

    monkeypatch.setattr(wiz, "AwsSetupWizard", FakeWizard)
    assert main(["aws-setup", "--yes", "--allow-delete", "--profile", "p1"]) == 0
    out = capsys.readouterr().out
    assert "detect" in out and "{POLICY-JSON}" in out
    assert calls == {"profile": "p1", "region": None, "allow_delete": True}


def test_aws_setup_failed_step_returns_1(capsys, monkeypatch):
    import keynest.services.aws_wizard as wiz

    class FakeWizard:
        def __init__(self, profile=None, region=None):
            pass

        def run_all(self, *, allow_delete_in_policy=False):
            return [wiz.WizardStep("identity", False, "no creds")]

    monkeypatch.setattr(wiz, "AwsSetupWizard", FakeWizard)
    assert main(["aws-setup", "--yes"]) == 1
    assert "FAIL" in capsys.readouterr().out
