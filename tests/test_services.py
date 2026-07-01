"""Tests for the service layer: dotenv, codegen, runner, audit, aws_policy, value_tools."""

from __future__ import annotations

import json
import sys
from typing import Any, cast

from keynest.model import SecretMap
from keynest.services import codegen, value_tools
from keynest.services.audit import AuditEvent, AuditLog
from keynest.services.aws_policy import generate_policy
from keynest.services.dotenv_parser import parse_dotenv, serialize_dotenv
from keynest.services.runner import build_environment, run_with_secrets


def _map(**values) -> SecretMap:
    return SecretMap(backend="os-keyring", folder="my-app", name="dev", values=values)


# -- dotenv ------------------------------------------------------------------


def test_parse_dotenv_basic():
    result = parse_dotenv('export A=1\nB="hello world" # note\n# comment\nC=\n')
    assert result.values == {"A": "1", "B": "hello world", "C": ""}


def test_parse_dotenv_inline_comment_only_when_unquoted():
    result = parse_dotenv("A=value # trailing\nB='# not a comment'")
    assert result.values["A"] == "value"
    assert result.values["B"] == "# not a comment"


def test_parse_dotenv_warns_on_bad_key():
    result = parse_dotenv("BAD-KEY=1")
    assert any("BAD-KEY" in w for w in result.warnings)


def test_dotenv_roundtrip_quotes_when_needed():
    text = serialize_dotenv({"A": "simple", "B": "has space", "C": 'q"uote'})
    parsed = parse_dotenv(text).values
    assert parsed == {"A": "simple", "B": "has space", "C": 'q"uote'}


# -- runner ------------------------------------------------------------------


def test_build_environment_merges_and_coerces():
    env = build_environment(_map(A="x", N=5, NONE=None), base_env={"EXISTING": "1"})
    assert env["A"] == "x"
    assert env["N"] == "5"
    assert env["EXISTING"] == "1"
    assert "NONE" not in env


def test_run_with_secrets_injects_env():
    rc = run_with_secrets(
        _map(KEYNEST_TEST_VAR="abc"),
        [sys.executable, "-c", "import os,sys; sys.exit(0 if os.environ.get('KEYNEST_TEST_VAR')=='abc' else 7)"],
    )
    assert rc == 0


# -- codegen -----------------------------------------------------------------


def test_codegen_never_references_keynest_runtime_import():
    sm = _map(DATABASE_URL="x", API_TOKEN="y")
    for snippet in codegen.all_snippets(sm):
        assert "import keynest" not in snippet.code
        assert "devsecrets_sdk" not in snippet.code


def test_codegen_includes_recommended_run_first():
    sm = _map(DATABASE_URL="x")
    snippets = codegen.all_snippets(sm)
    assert "keynest run my-app/dev" in snippets[0].code


def test_codegen_aws_secret_id():
    sm = _map(DATABASE_URL="x")
    boto = next(s for s in codegen.all_snippets(sm) if "boto3" in s.title)
    assert "devsecrets/my-app/dev" in boto.code


def test_raw_snippets_use_service_and_username_no_json():
    from keynest.model import RawCredential

    cred = RawCredential("git:https://github.com", "alice")
    snippets = codegen.raw_snippets(cred)
    py = next(s for s in snippets if s.language == "python")
    # Calls keyring.get_password with the raw identifiers, never JSON-parses.
    assert "keyring.get_password" in py.code
    assert "'git:https://github.com'" in py.code
    assert "'alice'" in py.code
    assert "json.loads" not in py.code
    # And never references keynest at runtime, like all snippets.
    assert "import keynest" not in py.code


def test_raw_snippets_handle_missing_username():
    from keynest.model import RawCredential

    snippets = codegen.raw_snippets(RawCredential("AWS", None))
    py = next(s for s in snippets if s.language == "python")
    assert "''" in py.code  # empty-string username, not "None"
    assert "None" not in py.code.split("get_password")[1].split(")")[0]


# -- aws policy --------------------------------------------------------------


def test_generate_policy_scopes_resource():
    policy = generate_policy("us-east-1", "123456789012", folder="my-app")
    statements = cast(list[dict[str, Any]], policy["Statement"])
    manage = statements[0]
    assert manage["Resource"].endswith("secret:devsecrets/my-app/*")
    assert "secretsmanager:GetSecretValue" in manage["Action"]
    # delete excluded by default
    assert "secretsmanager:DeleteSecret" not in manage["Action"]


def test_generate_policy_allow_delete():
    policy = generate_policy("us-east-1", "123456789012", allow_delete=True)
    statements = cast(list[dict[str, Any]], policy["Statement"])
    assert "secretsmanager:DeleteSecret" in statements[0]["Action"]


# -- value tools -------------------------------------------------------------


def test_password_length_and_uniqueness():
    assert len(value_tools.generate_password(32)) == 32
    assert value_tools.generate_password() != value_tools.generate_password()


def test_validators():
    assert value_tools.validate_url("https://x/y") is None
    assert value_tools.validate_url("nohost") is not None
    assert value_tools.validate_json('{"a":1}') is None
    assert value_tools.validate_json("{nope}") is not None
    assert value_tools.validate_pem("-----BEGIN X-----\n-----END X-----") is None


# -- audit -------------------------------------------------------------------


def test_audit_records_event_without_value(tmp_path):
    log = AuditLog(path=tmp_path / "audit.log")
    log.record(AuditEvent(action="copy", backend="os-keyring", folder="f", name="n", key="K"))
    events = log.events()
    assert len(events) == 1
    assert events[0].key == "K"
    # The raw file must not contain anything that looks like a value field.
    raw = (tmp_path / "audit.log").read_text()
    assert "value" not in json.loads(raw.splitlines()[0])
