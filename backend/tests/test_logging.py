import json

import structlog

from app.core.logging import configure_logging, redact_secrets


def test_sensitive_keys_redacted():
    event = {"event": "x", "access_token": "abc", "nested": {"api_secret": "s", "ok": 1}}
    out = redact_secrets(None, "info", event)
    assert out["access_token"] == "[REDACTED]"
    assert out["nested"] == {"api_secret": "[REDACTED]", "ok": 1}


def test_inline_bearer_and_url_credentials_redacted():
    out = redact_secrets(None, "info", {"event": "GET with Bearer eyJabc.def-ghi",
                                        "dsn": "postgresql://user:pw123@host/db"})
    assert "eyJabc" not in out["event"]
    assert "pw123" not in out["dsn"] and out["dsn"].startswith("postgresql://user:")


def test_json_log_output(capsys):
    configure_logging("INFO", json=True)
    structlog.get_logger("t").info("hello", password="p", n=1)
    line = capsys.readouterr().out.strip().splitlines()[-1]
    rec = json.loads(line)
    assert rec["event"] == "hello" and rec["password"] == "[REDACTED]" and rec["level"] == "info"
