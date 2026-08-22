"""Append-only structured audit records with sensitive-field redaction."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SENSITIVE_KEYS = {"token", "password", "secret", "api_key", "apikey", "cookie", "authorization"}


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "<redacted>" if key.lower() in SENSITIVE_KEYS else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class AuditLogger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def record(self, *, tool: str, workspace: str | None, risk: str, approved: bool, success: bool, details: dict[str, Any] | None = None) -> None:
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "workspace": workspace,
            "risk": risk,
            "approved": approved,
            "success": success,
            "details": redact(details or {}),
        }
        with self._lock:
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
