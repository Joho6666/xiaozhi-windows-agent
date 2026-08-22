import json

from security.audit import AuditLogger, redact


def test_redact_can_be_used_for_permission_descriptions():
    assert 'secret' not in str(redact({"token": "secret", "nested": {"password": "pw"}}))


def test_audit_logger_writes_structured_redacted_jsonl(tmp_path):
    logger = AuditLogger(tmp_path / "audit.jsonl")
    logger.record(
        tool="git_status",
        workspace="agent",
        risk="READ",
        approved=True,
        success=True,
        details={"message": "ok", "token": "secret", "password": "secret2"},
    )
    row = json.loads((tmp_path / "audit.jsonl").read_text(encoding="utf-8"))
    assert row["tool"] == "git_status"
    assert row["details"]["token"] == "<redacted>"
    assert row["details"]["password"] == "<redacted>"
